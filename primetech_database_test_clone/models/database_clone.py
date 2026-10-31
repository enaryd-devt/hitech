# -*- coding: utf-8 -*-

import base64
import calendar
import hashlib
import logging
import os
import posixpath
import re
import shutil
import tempfile
import threading
import time as time_module
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

import pytz

from odoo import SUPERUSER_ID, _, api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.modules.registry import Registry
from odoo.service import db

from . import fast_clone
from .database_clone_config import get_config

_logger = logging.getLogger(__name__)


class BackupFailed(UserError):
    """Raised once the failure has already been recorded in the journal."""


def _run_manual_plan_thread(dbname, plan_id, uid, do_backup, do_clone):
    """Run a manually launched plan outside the HTTP request."""
    current = threading.current_thread()
    current.dbname = dbname
    current.uid = uid
    try:
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            plan = env["primetech.database.clone.plan"].with_context(active_test=False).browse(plan_id)
            plan._run_claimed("manual", env["res.users"].browse(uid), do_backup, do_clone)
    except Exception:
        _logger.exception("Primetech manual backup thread failed for plan %s", plan_id)

WEEKDAYS = [
    ("0", "Lundi"),
    ("1", "Mardi"),
    ("2", "Mercredi"),
    ("3", "Jeudi"),
    ("4", "Vendredi"),
    ("5", "Samedi"),
    ("6", "Dimanche"),
]


class PrimetechDatabaseCloneLog(models.Model):
    _name = "primetech.database.clone.log"
    _description = "Journal de sauvegarde et copie de test"
    _order = "create_date desc"

    create_date = fields.Datetime(string="Date", readonly=True)
    source_database = fields.Char(string="Base de production", required=True, readonly=True)
    test_database = fields.Char(string="Base de test", required=True, readonly=True)
    backup_path = fields.Char(string="Fichier de sauvegarde", readonly=True)
    backup_size = fields.Integer(string="Taille (octets)", readonly=True)
    backup_deleted = fields.Boolean(string="Archive supprimée", readonly=True)
    duration = fields.Float(string="Durée (s)", readonly=True, digits=(16, 0))
    do_backup = fields.Boolean(string="Sauvegarde", readonly=True)
    do_clone = fields.Boolean(string="Copie vers la base de test", readonly=True)
    state = fields.Selection(
        [("running", "En cours"), ("done", "Terminé"), ("failed", "Échec")],
        string="État",
        required=True,
        default="running",
        readonly=True,
    )
    message = fields.Text(string="Détail", readonly=True)
    user_id = fields.Many2one("res.users", string="Lancé par", readonly=True)
    trigger = fields.Selection(
        [("manual", "Manuel"), ("automatic", "Automatique")],
        string="Déclenchement",
        default="manual",
        readonly=True,
    )
    plan_id = fields.Many2one("primetech.database.clone.plan", string="Planification", readonly=True)

    @api.model
    def _parameter(self, name, default=False):
        return self.env["ir.config_parameter"].sudo().get_param(name, default)

    @api.model
    def _validate_target_database(self, source_database, target_database):
        if not target_database or not re.fullmatch(r"[A-Za-z0-9_]+", target_database):
            raise ValidationError(_(
                "Le nom de la base de test ne peut contenir que des lettres, chiffres et traits bas."
            ))
        if source_database == target_database:
            raise ValidationError(_(
                "La base de test doit être différente de la base de production."
            ))

    @api.model
    def _backup_directory(self, plan=False):
        folder = (plan and plan.backup_path) or self._parameter(
            "primetech_database_test_clone.backup_path",
            os.path.join(tools.config["data_dir"], "primetech_backups"),
        )
        folder = os.path.abspath(os.path.expanduser(folder))
        filestore = os.path.abspath(tools.config.filestore(self.env.cr.dbname))
        if folder == filestore or folder.startswith(filestore + os.sep):
            raise ValidationError(_(
                "Le dossier de sauvegarde ne peut pas être placé dans le filestore Odoo."
            ))
        os.makedirs(folder, exist_ok=True)
        return folder

    @api.model
    def _now_in_timezone(self, plan=False):
        timezone_name = (plan and plan.timezone) or self._parameter(
            "primetech_database_test_clone.timezone", "Africa/Douala"
        )
        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError as exc:
            raise ValidationError(_("Fuseau horaire invalide : %s") % timezone_name) from exc
        return datetime.now(pytz.utc).astimezone(timezone)

    @api.model
    def _generate_backup_filename(self, source_database, plan=False):
        timestamp = self._now_in_timezone(plan).strftime("%Y%m%d_%H%M%S")
        return "%s_%s.dump.zip" % (source_database, timestamp)

    @api.model
    def _old_backup_names(self, filenames, source_database, retention_count):
        """Return the archive names exceeding the N most recent ones."""
        if retention_count <= 0:
            return []
        pattern = re.compile(r"%s_(\d{8}_\d{6})\.dump\.zip" % re.escape(source_database))
        backups = sorted(
            (match.group(1), filename)
            for filename in filenames
            for match in [pattern.fullmatch(filename)]
            if match
        )
        return [filename for _timestamp, filename in backups[:-retention_count]]

    @api.model
    def _retention_count(self, plan=False):
        return plan.retention_count if plan else int(self._parameter(
            "primetech_database_test_clone.retention_count", 7
        ) or 0)

    @api.model
    def _purge_old_backups(self, folder, source_database, plan=False):
        """Keep only the N most recent local archives of ``source_database``.

        Only files named ``<source>_YYYYMMDD_HHMMSS.dump.zip`` are considered,
        so other files stored in the folder are never touched.
        """
        deleted = []
        for filename in self._old_backup_names(os.listdir(folder), source_database, self._retention_count(plan)):
            path = os.path.join(folder, filename)
            try:
                os.remove(path)
            except OSError:
                _logger.exception("Unable to delete old backup %s", path)
                continue
            deleted.append(path)
        self._mark_deleted(deleted)
        return deleted

    @api.model
    def _mark_deleted(self, paths):
        if paths:
            self.sudo().search([("backup_path", "in", paths)]).write({"backup_deleted": True})
            _logger.info("Deleted %s old backup(s)", len(paths))

    @api.model
    def _send_archive(self, archive_path, sftp_values, source_database, retention_count):
        """Upload the archive to the SFTP server and apply the retention there.

        Runs in a worker thread: only plain values are used, no ORM access.
        """
        with fast_clone.Sftp(
            sftp_values["host"], sftp_values["port"], sftp_values["user"],
            sftp_values["password"], sftp_values["host_key"],
        ) as sftp:
            remote_path = sftp.upload(archive_path, sftp_values["path"])
            deleted = []
            for filename in self._old_backup_names(
                sftp.listdir(sftp_values["path"]), source_database, retention_count
            ):
                path = posixpath.join(sftp_values["path"], filename)
                try:
                    sftp.remove(path)
                except OSError:
                    _logger.exception("Unable to delete remote backup %s", path)
                    continue
                deleted.append(path)
            return {
                "remote_path": remote_path,
                "deleted": deleted,
                "new_host_key": sftp.host_key if sftp.new_host_key else False,
            }

    @api.model
    def action_run_backup_and_clone(self, plan=False, requested_by=False, trigger="manual",
                                    do_backup=True, do_clone=True):
        """Save an archive of production and/or replace the test database.

        Production is dumped only once, with parallel jobs. The test database
        restoration and the archive creation / upload then run at the same time.
        At most one archive per execution is kept, locally or on the SFTP server.
        """
        in_background = self.env.context.get("primetech_database_clone_cron")
        if (
            not in_background
            and not self.env.user.has_group(
                "primetech_database_test_clone.group_database_test_clone_manager"
            )
        ):
            raise AccessError(_("Vous n'avez pas accès aux sauvegardes et bases de test."))
        if not (do_backup or do_clone):
            raise UserError(_("Choisissez au moins une action : sauvegarde ou copie vers la base de test."))

        source_database = self.env.cr.dbname
        plan = plan or self.env["primetech.database.clone.plan"].browse(
            self.env.context.get("primetech_clone_plan_id")
        ).exists()
        target_database = False
        if do_clone:
            target_database = (plan and plan.test_database) or self._parameter(
                "primetech_database_test_clone.test_database"
            )
            self._validate_target_database(source_database, target_database)
        jobs = max(1, min(plan.parallel_jobs if plan else 4, 16))
        remote = bool(do_backup and plan and plan.destination == "sftp")
        sftp_values = plan.sudo()._sftp_values() if remote else False
        retention_count = self._retention_count(plan)

        backup_folder = self._backup_directory(plan)
        work_dir = tempfile.mkdtemp(prefix=".%s_travail_" % source_database, dir=backup_folder)
        dump_dir = os.path.join(work_dir, "dump")
        archive_name = self._generate_backup_filename(source_database, plan)
        archive_path = os.path.join(work_dir if remote else backup_folder, archive_name)
        if remote:
            final_path = plan._sftp_url(posixpath.join(sftp_values["path"], archive_name))
        else:
            final_path = archive_path if do_backup else False

        log = self.sudo().create({
            "source_database": source_database,
            "test_database": target_database or "-",
            "backup_path": final_path,
            "do_backup": do_backup,
            "do_clone": do_clone,
            "user_id": (requested_by or self.env.user).id,
            "trigger": trigger,
            "plan_id": plan.id if plan else False,
            "state": "running",
            "message": _("Exécution en cours."),
        })
        if in_background:
            # Make the running entry visible in the journal during the backup.
            self.env.cr.commit()

        timings = {}
        started = time_module.monotonic()

        def timed(label, function, *args):
            step_start = time_module.monotonic()
            result = function(*args)
            timings[label] = time_module.monotonic() - step_start
            return result

        def archive_and_send():
            timed("archive", fast_clone.build_odoo_archive, source_database, dump_dir, archive_path)
            if remote:
                return timed("envoi SFTP", self._send_archive, archive_path, sftp_values,
                             source_database, retention_count)
            return None

        sent = None
        archive_size = 0
        try:
            timed("export", fast_clone.dump_directory, source_database, dump_dir, jobs)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="primetech_clone") as pool:
                futures = {}
                if do_clone:
                    futures["clone"] = pool.submit(
                        timed, "base de test", fast_clone.restore_test_database,
                        source_database, target_database, dump_dir, jobs,
                    )
                if do_backup:
                    futures["backup"] = pool.submit(archive_and_send)
                errors = []
                for key, future in futures.items():
                    try:
                        result = future.result()
                        if key == "backup":
                            sent = result
                    except Exception as exc:
                        errors.append((key, exc))
            if do_backup and os.path.exists(archive_path):
                archive_size = os.path.getsize(archive_path)
            if errors:
                raise errors[0][1]
        except Exception as exc:
            _logger.exception("Primetech database backup/test clone failed")
            message = str(exc)
            archive_done = "archive" in timings
            kept_path = False
            if do_backup and remote and archive_done and os.path.exists(archive_path):
                # The upload failed but the archive is complete: keep it
                # locally rather than losing this backup.
                kept_path = os.path.join(backup_folder, archive_name)
                shutil.move(archive_path, kept_path)
                message += "\n" + _("L'archive a été conservée localement : %s") % kept_path
            elif do_backup and not remote and not archive_done and os.path.exists(archive_path):
                os.remove(archive_path)  # incomplete archive
            kept_path = kept_path or (archive_path if do_backup and not remote and archive_done else False)
            log.write({
                "state": "failed",
                "backup_path": kept_path,
                "backup_size": os.path.getsize(kept_path) if kept_path else 0,
                "duration": time_module.monotonic() - started,
                "message": message,
            })
            if in_background:
                self.env.cr.commit()
            raise BackupFailed(_("L'exécution a échoué : %s") % exc) from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        duration = time_module.monotonic() - started
        if do_backup and do_clone:
            message = _(
                "Sauvegarde enregistrée puis base de test '%s' remplacée avec succès. "
                "Les actions sortantes de la copie ont été neutralisées."
            ) % target_database
        elif do_backup:
            message = _("Sauvegarde enregistrée avec succès (base de test non modifiée).")
        else:
            message = _(
                "Base de test '%s' remplacée par une copie de la production (aucune sauvegarde "
                "conservée). Les actions sortantes de la copie ont été neutralisées."
            ) % target_database
        if remote:
            message += "\n" + _("Archive envoyée sur le serveur distant : %s") % final_path
        message += "\n" + _("Durée totale : %(total).0f s (%(steps)s), %(jobs)s processus parallèles.") % {
            "total": duration,
            "steps": ", ".join("%s %.0f s" % (label, seconds) for label, seconds in timings.items()),
            "jobs": jobs,
        }
        log.write({"state": "done", "backup_size": archive_size, "duration": duration, "message": message})

        # Old archives are purged only after a successful backup, so a failing
        # execution never leaves the destination without recent copies.
        if do_backup:
            try:
                if remote:
                    deleted = [plan._sftp_url(path) for path in sent["deleted"]]
                    self._mark_deleted(deleted)
                    if sent["new_host_key"]:
                        plan.sudo().sftp_host_key = sent["new_host_key"]
                else:
                    deleted = self._purge_old_backups(backup_folder, source_database, plan)
            except Exception as exc:
                _logger.exception("Primetech old backups purge failed")
                log.write({"message": message + "\n" + _("Purge des anciennes sauvegardes impossible : %s") % exc})
            else:
                if deleted:
                    log.write({"message": message + "\n" + _(
                        "Conservation limitée à %s sauvegarde(s) : %s ancienne(s) supprimée(s) :\n%s"
                    ) % (retention_count, len(deleted), "\n".join(deleted))})
        return log

    @api.model
    def _cron_run_backup_and_clone(self):
        """Run the automatic executions that are due.

        Manual launches do not go through this cron: they start immediately
        in their own thread (see ``action_run_now``).
        """
        Plan = self.env["primetech.database.clone.plan"].sudo().with_context(active_test=False)
        now = fields.Datetime.now()
        # Release executions interrupted by a server restart.
        Plan.search([
            ("execution_state", "=", "running"),
            ("run_started_at", "<", now - timedelta(hours=get_config(self.env, "running_timeout_hours"))),
        ]).write({
            "execution_state": "idle",
            "running_trigger": False,
            "run_started_at": False,
            "requested_by_id": False,
        })
        self.env.cr.commit()
        for plan in Plan.search([("active", "=", True)]):
            if not plan.next_run_date:
                plan.next_run_date = plan._get_next_run_date(now)
                self.env.cr.commit()
            if plan.next_run_date > now:
                continue
            if not plan._claim():
                self.env.cr.rollback()
                continue
            self.env.cr.commit()
            plan._run_claimed("automatic")


class PrimetechDatabaseClonePlan(models.Model):
    _name = "primetech.database.clone.plan"
    _description = "Planification de sauvegarde et base de test"
    _order = "active desc, name"

    name = fields.Char(string="Nom", required=True, default=lambda self: self._default_name())
    # A new plan starts stopped: it only runs once explicitly started.
    active = fields.Boolean(string="Actif", default=False)
    backup_path = fields.Char(
        string="Dossier des sauvegardes",
        required=True,
        default=lambda self: self._default_backup_path(),
    )
    test_database = fields.Char(
        string="Base de test", required=True,
        default=lambda self: get_config(self.env, "default_test_database"),
    )
    frequency = fields.Selection(
        [("daily", "Chaque jour"), ("weekly", "Chaque semaine"), ("monthly", "Chaque mois")],
        string="Fréquence",
        required=True,
        default="daily",
    )
    weekday = fields.Selection(
        WEEKDAYS,
        string="Jour de la semaine",
        default="6",
        help="Utilisé pour une exécution hebdomadaire.",
    )
    month_day = fields.Integer(
        string="Jour du mois",
        default=1,
        help="Utilisé pour une exécution mensuelle. Si le mois est plus court, "
             "l'exécution a lieu le dernier jour du mois.",
    )
    planned_hour = fields.Float(
        string="Heure d'exécution",
        required=True,
        default=lambda self: get_config(self.env, "default_planned_hour"),
        help="Choisissez une heure de faible activité : la sauvegarde s'exécute en arrière-plan "
             "mais consomme des ressources du serveur.",
    )
    next_run_date = fields.Datetime(string="Prochaine exécution", readonly=True, copy=False)
    execution_state = fields.Selection(
        [("idle", "En attente"), ("running", "En cours")],
        string="État d'exécution",
        required=True,
        readonly=True,
        copy=False,
        default="idle",
    )
    running_trigger = fields.Selection(
        [("manual", "Manuelle"), ("automatic", "Automatique")],
        string="Exécution en cours",
        readonly=True,
        copy=False,
    )
    requested_by_id = fields.Many2one("res.users", string="Demandée par", readonly=True, copy=False)
    run_started_at = fields.Datetime(string="Démarrée le", readonly=True, copy=False)
    do_backup = fields.Boolean(
        string="Enregistrer une sauvegarde",
        default=True,
        help="Enregistre une archive complète de la base de production dans le dossier des sauvegardes.",
    )
    do_clone = fields.Boolean(
        string="Remplacer la base de test",
        default=True,
        help="Duplique la base de production en cours pour remplacer la base de test "
             "(actions sortantes neutralisées).",
    )
    destination = fields.Selection(
        [("local", "Dossier local du serveur"), ("sftp", "Ordinateur distant (SSH / SFTP)")],
        string="Destination des sauvegardes",
        required=True,
        default="local",
        help="Ordinateur distant : l'archive est envoyée par SSH (SFTP) avec mot de passe, par exemple "
             "sur un disque dur externe branché à cet ordinateur. Elle n'est alors pas conservée localement.",
    )
    sftp_host = fields.Char(string="Adresse du serveur distant", help="Nom ou adresse IP de l'ordinateur distant.")
    sftp_port = fields.Integer(string="Port SSH", default=22)
    sftp_user = fields.Char(string="Utilisateur SSH")
    sftp_password = fields.Char(
        string="Mot de passe SSH",
        groups="primetech_database_test_clone.group_database_test_clone_manager",
        copy=False,
    )
    sftp_path = fields.Char(
        string="Dossier distant",
        help="Dossier de destination sur l'ordinateur distant, par exemple /media/disque_externe/odoo "
             "ou /E:/Sauvegardes sur un serveur SSH Windows. Il est créé s'il n'existe pas.",
    )
    sftp_host_key = fields.Char(
        string="Clé du serveur",
        readonly=True,
        copy=False,
        groups="primetech_database_test_clone.group_database_test_clone_manager",
        help="Enregistrée à la première connexion puis vérifiée à chaque envoi, pour refuser un serveur usurpé.",
    )
    sftp_fingerprint = fields.Char(string="Empreinte du serveur", compute="_compute_sftp_fingerprint")
    parallel_jobs = fields.Integer(
        string="Processus parallèles",
        default=lambda self: get_config(self.env, "default_parallel_jobs"),
        help="Nombre de processus PostgreSQL utilisés en parallèle pour l'export et la restauration. "
             "Plus il est élevé, plus l'exécution est rapide, mais plus le serveur est sollicité (1 à 16).",
    )
    retention_count = fields.Integer(
        string="Nombre de sauvegardes conservées",
        required=True,
        default=lambda self: get_config(self.env, "default_retention_count"),
        help="Après chaque nouvelle sauvegarde, seules les N plus récentes sont gardées sur le disque : "
             "les plus anciennes sont supprimées, que l'exécution soit manuelle ou automatique. "
             "0 = conserver toutes les sauvegardes.",
    )
    timezone = fields.Selection(
        selection=lambda self: [(timezone, timezone) for timezone in sorted(set(pytz.all_timezones))],
        string="Fuseau horaire",
        required=True,
        default=lambda self: get_config(self.env, "default_timezone"),
    )
    last_run_date = fields.Date(string="Dernière exécution", readonly=True, copy=False)
    log_ids = fields.One2many("primetech.database.clone.log", "plan_id", string="Journal")
    status = fields.Selection(
        [
            ("new", "Nouvelle"),
            ("stopped", "Arrêtée"),
            ("scheduled", "En cours – en attente de la prochaine exécution"),
            ("running", "En cours d'exécution"),
        ],
        string="Statut",
        compute="_compute_status",
        store=True,
    )

    def _existing_plans(self):
        return self.sudo().with_context(active_test=False).search([])

    @api.model
    def _default_name(self):
        names = set(self._existing_plans().mapped("name"))
        number = len(names) + 1
        while _("Planification %s") % number in names:
            number += 1
        return _("Planification %s") % number

    @api.model
    def _default_backup_path(self):
        """A folder of its own, so that a new plan never shares the retention
        of another plan's backups."""
        root = get_config(self.env, "default_backup_root")
        used = {
            os.path.normcase(os.path.abspath(path))
            for path in self._existing_plans().mapped("backup_path") if path
        }
        if os.path.normcase(os.path.abspath(root)) not in used:
            return root
        number = 2
        while os.path.normcase(os.path.abspath(os.path.join(root, "planification_%s" % number))) in used:
            number += 1
        return os.path.join(root, "planification_%s" % number)

    @api.depends("active", "execution_state")
    def _compute_status(self):
        for plan in self:
            if not plan.id:
                # Not saved yet: no schedule, no execution.
                plan.status = "new"
            elif plan.execution_state == "running":
                plan.status = "running"
            else:
                plan.status = "scheduled" if plan.active else "stopped"

    @api.constrains("test_database")
    def _check_test_database(self):
        for plan in self:
            self.env["primetech.database.clone.log"]._validate_target_database(
                self.env.cr.dbname, plan.test_database
            )

    @api.constrains("retention_count")
    def _check_retention_count(self):
        for plan in self:
            if plan.retention_count < 0:
                raise ValidationError(_("Le nombre de sauvegardes conservées ne peut pas être négatif."))

    blocking_plan_id = fields.Many2one(
        "primetech.database.clone.plan",
        string="Autre exécution en cours",
        compute="_compute_blocking_plan_id",
    )

    def _compute_blocking_plan_id(self):
        running = self.sudo().with_context(active_test=False).search([("execution_state", "=", "running")])
        for plan in self:
            plan.blocking_plan_id = (running - plan)[:1]

    @api.depends("sftp_host_key")
    def _compute_sftp_fingerprint(self):
        for plan in self:
            key = plan.sudo().sftp_host_key
            if key and " " in key:
                digest = hashlib.sha256(base64.b64decode(key.split(" ", 1)[1])).digest()
                plan.sftp_fingerprint = "%s SHA256:%s" % (
                    key.split(" ", 1)[0], base64.b64encode(digest).decode().rstrip("=")
                )
            else:
                plan.sftp_fingerprint = False

    def _destination_key(self):
        """Identify where the plan stores its archives (None without backup)."""
        self.ensure_one()
        if not self.do_backup:
            return None
        if self.destination == "sftp":
            path = posixpath.normpath((self.sftp_path or "").replace("\\", "/"))
            return ("sftp", (self.sftp_host or "").strip().lower(), self.sftp_port or 22, path)
        return ("local", os.path.normcase(os.path.abspath(os.path.expanduser(self.backup_path or ""))))

    @api.constrains("do_backup", "destination", "backup_path", "sftp_host", "sftp_port", "sftp_path")
    def _check_unique_destination(self):
        """Each plan applies its retention to its own folder: two plans sharing
        a folder would delete each other's backups."""
        others = self.with_context(active_test=False).search([])
        for plan in self:
            key = plan._destination_key()
            if key is None:
                continue
            for other in others - plan:
                if other._destination_key() == key:
                    raise ValidationError(_(
                        "La planification « %(other)s » enregistre déjà ses sauvegardes dans ce dossier. "
                        "Chaque planification doit avoir son propre dossier (local ou distant), car elle y "
                        "applique son propre nombre de sauvegardes conservées."
                    ) % {"other": other.name})

    def copy_data(self, default=None):
        """A copy gets its own name and folder, ready to target another computer."""
        vals_list = super().copy_data(default=default)
        for plan, vals in zip(self, vals_list):
            if default and "name" in default:
                continue
            vals["name"] = _("%s (copie)") % plan.name
            vals["active"] = False
            vals["backup_path"] = self._default_backup_path()
            if plan.sftp_path:
                vals["sftp_path"] = plan.sftp_path.rstrip("/") + "_copie"
        return vals_list

    @api.constrains("parallel_jobs")
    def _check_parallel_jobs(self):
        for plan in self:
            if not 1 <= plan.parallel_jobs <= 16:
                raise ValidationError(_("Le nombre de processus parallèles doit être compris entre 1 et 16."))

    @api.constrains("destination", "sftp_host", "sftp_user", "sftp_path", "sftp_port")
    def _check_sftp(self):
        for plan in self:
            if plan.destination != "sftp":
                continue
            if not (plan.sftp_host and plan.sftp_user and plan.sftp_path):
                raise ValidationError(_(
                    "Pour une destination distante, indiquez l'adresse, l'utilisateur et le dossier distant."
                ))
            if not 1 <= plan.sftp_port <= 65535:
                raise ValidationError(_("Le port SSH doit être compris entre 1 et 65535."))

    def _sftp_values(self):
        self.ensure_one()
        plan = self.sudo()
        return {
            "host": plan.sftp_host,
            "port": plan.sftp_port or 22,
            "user": plan.sftp_user,
            "password": plan.sftp_password or "",
            "path": (plan.sftp_path or "").replace("\\", "/"),
            "host_key": plan.sftp_host_key or False,
        }

    def _sftp_url(self, remote_path):
        self.ensure_one()
        return "sftp://%s@%s:%s%s%s" % (
            self.sftp_user, self.sftp_host, self.sftp_port or 22,
            "" if remote_path.startswith("/") else "/", remote_path,
        )

    def action_test_sftp(self):
        """Connect, create the remote folder and write / delete a test file."""
        self.ensure_one()
        self._check_manager()
        if not (self.sftp_host and self.sftp_user and self.sftp_path):
            raise UserError(_("Indiquez l'adresse, l'utilisateur et le dossier distant."))
        values = self._sftp_values()
        try:
            with fast_clone.Sftp(values["host"], values["port"], values["user"],
                                 values["password"], values["host_key"]) as sftp:
                new_key = sftp.host_key if sftp.new_host_key else False
                if new_key:
                    # The connection itself succeeded: keep the server key
                    # even if the folder check below fails.
                    self.sudo().sftp_host_key = new_key
                    self.env.cr.commit()
                sftp.makedirs(values["path"])
                sftp.check_writable(values["path"])
        except fast_clone.RemoteAccessError as exc:
            raise UserError(str(exc)) from exc
        except Exception as exc:
            raise UserError(_("Connexion SSH impossible : %s") % exc) from exc
        return self._notify(
            _("Connexion réussie : le dossier distant %(path)s est accessible en écriture.%(key)s") % {
                "path": values["path"],
                "key": _(" Clé du serveur enregistrée : %s") % self.sftp_fingerprint if new_key else "",
            },
            "success",
        )

    def action_forget_host_key(self):
        self._check_manager()
        self.sudo().sftp_host_key = False
        return self._notify(_("Clé du serveur effacée : elle sera enregistrée à la prochaine connexion."), "warning")

    @api.constrains("do_backup", "do_clone")
    def _check_actions(self):
        for plan in self:
            if not (plan.do_backup or plan.do_clone):
                raise ValidationError(_(
                    "Cochez au moins une action : enregistrer une sauvegarde ou remplacer la base de test."
                ))

    @api.constrains("planned_hour")
    def _check_planned_hour(self):
        for plan in self:
            if plan.planned_hour < 0 or plan.planned_hour >= 24:
                raise ValidationError(_("L'heure d'exécution doit être comprise entre 00:00 et 23:59."))

    @api.constrains("frequency", "weekday", "month_day")
    def _check_schedule(self):
        for plan in self:
            if plan.frequency == "weekly" and not plan.weekday:
                raise ValidationError(_("Indiquez le jour de la semaine de l'exécution."))
            if plan.frequency == "monthly" and not 1 <= plan.month_day <= 31:
                raise ValidationError(_("Le jour du mois doit être compris entre 1 et 31."))

    def _get_next_run_date(self, after):
        """Return the next scheduled run (naive UTC) strictly after ``after``."""
        self.ensure_one()
        timezone = pytz.timezone(self.timezone)
        local_after = pytz.utc.localize(after).astimezone(timezone).replace(tzinfo=None)
        hours, minutes = divmod(round(self.planned_hour * 60), 60)
        day = local_after.date()
        for _offset in range(400):
            if self.frequency == "weekly":
                matches = day.weekday() == int(self.weekday)
            elif self.frequency == "monthly":
                last_day = calendar.monthrange(day.year, day.month)[1]
                matches = day.day == min(self.month_day, last_day)
            else:
                matches = True
            candidate = datetime.combine(day, time(hours, minutes))
            if matches and candidate > local_after:
                return timezone.localize(candidate).astimezone(pytz.utc).replace(tzinfo=None)
            day += timedelta(days=1)
        return False

    @api.model_create_multi
    def create(self, vals_list):
        plans = super().create(vals_list)
        now = fields.Datetime.now()
        for plan in plans:
            plan.next_run_date = plan._get_next_run_date(now)
        return plans

    def write(self, vals):
        if {"sftp_host", "sftp_port"} & set(vals):
            # Another server: its key must be recorded again.
            vals = dict(vals, sftp_host_key=False)
        schedule_fields ={"frequency", "weekday", "month_day", "planned_hour", "timezone", "active"}
        changed = self.filtered(
            lambda plan: any(
                field in vals and plan[field] != vals[field] for field in schedule_fields
            )
        ) if schedule_fields & set(vals) else self.browse()
        result = super().write(vals)
        now = fields.Datetime.now()
        for plan in changed:
            plan.next_run_date = plan._get_next_run_date(now)
        return result

    def _running_plans(self):
        """Other plans currently executing (whatever their state is)."""
        return self.sudo().with_context(active_test=False).search([
            ("id", "not in", self.ids),
            ("execution_state", "=", "running"),
        ])

    def _claim(self, requested_by=False, trigger="automatic"):
        """Mark the plan as running, unless an execution is already in progress.

        Only one plan runs at a time: several plans then never export production
        simultaneously, nor replace the same test database at the same time.
        The transaction-level advisory lock serializes concurrent claims (manual
        launches and cron) until the "running" state is committed.
        """
        self.ensure_one()
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext('primetech_database_clone_claim'))")
        self.invalidate_model(["execution_state"])
        if self.execution_state == "running" or self._running_plans():
            return False
        self.sudo().write({
            "execution_state": "running",
            "running_trigger": trigger,
            "run_started_at": fields.Datetime.now(),
            "requested_by_id": requested_by.id if requested_by else False,
        })
        return True

    def _run_claimed(self, trigger, requested_by=False, do_backup=None, do_clone=None):
        """Run a claimed plan, then release it. Commits its own work.

        Without explicit options, the plan's own options are used (automatic run).
        """
        self.ensure_one()
        plan = self.sudo()
        do_backup = plan.do_backup if do_backup is None else do_backup
        do_clone = plan.do_clone if do_clone is None else do_clone
        Log = self.env["primetech.database.clone.log"].sudo().with_context(primetech_database_clone_cron=True)
        try:
            Log.action_run_backup_and_clone(
                plan=plan, requested_by=requested_by, trigger=trigger,
                do_backup=do_backup, do_clone=do_clone,
            )
        except BackupFailed:
            # Already recorded in the journal.
            self.env.cr.rollback()
        except Exception as exc:
            self.env.cr.rollback()
            _logger.exception("Primetech backup could not start for plan %s", plan.id)
            Log.create({
                "source_database": self.env.cr.dbname,
                "test_database": plan.test_database if do_clone else "-",
                "do_backup": do_backup,
                "do_clone": do_clone,
                "user_id": (requested_by or self.env.user).id,
                "trigger": trigger,
                "plan_id": plan.id,
                "state": "failed",
                "message": str(exc),
            })
        values = {
            "execution_state": "idle",
            "running_trigger": False,
            "run_started_at": False,
            "requested_by_id": False,
            "last_run_date": Log._now_in_timezone(plan).date(),
        }
        if trigger == "automatic":
            values["next_run_date"] = plan._get_next_run_date(fields.Datetime.now())
        plan.write(values)
        self.env.cr.commit()

    def action_run_now(self):
        """Open the assistant asking which actions the manual run performs."""
        self.ensure_one()
        self._check_manager()
        if self.execution_state == "running":
            raise UserError(_("Une exécution de cette planification est déjà en cours."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Exécution manuelle"),
            "res_model": "primetech.database.clone.run.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_plan_id": self.id,
                "default_do_backup": self.do_backup,
                "default_do_clone": self.do_clone,
            },
        }

    def _launch_manual(self, do_backup, do_clone):
        """Manual launch: starts immediately, in a separate thread so the user
        is not blocked, even when the automatic schedule is stopped."""
        self.ensure_one()
        self._check_manager()
        if not (do_backup or do_clone):
            raise UserError(_("Cochez au moins une action à exécuter."))
        if not self._claim(self.env.user, "manual"):
            other = self._running_plans()
            if other and self.execution_state != "running":
                raise UserError(_(
                    "La planification « %s » est en cours d'exécution. Pour ne pas surcharger le serveur, "
                    "une seule exécution a lieu à la fois : relancez celle-ci quand elle sera terminée."
                ) % other[0].name)
            raise UserError(_("Une exécution de cette planification est déjà en cours."))
        dbname, plan_id, uid = self.env.cr.dbname, self.id, self.env.uid

        def start_thread():
            threading.Thread(
                target=_run_manual_plan_thread,
                args=(dbname, plan_id, uid, do_backup, do_clone),
                name="primetech_database_clone_%s" % plan_id,
                daemon=True,
            ).start()

        # Start only once the "running" state is committed and visible.
        self.env.cr.postcommit.add(start_thread)
        return self._notify(_(
            "Exécution manuelle démarrée en arrière-plan. Vous pouvez continuer à travailler ; "
            "le résultat apparaîtra dans le Journal."
        ))

    def _check_manager(self):
        if not self.env.user.has_group("primetech_database_test_clone.group_database_test_clone_manager"):
            raise AccessError(_("Vous n'avez pas accès aux sauvegardes et bases de test."))

    def _notify(self, message, notification_type="info"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sauvegarde et base de test"),
                "message": message,
                "type": notification_type,
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_start(self):
        """Enable the automatic schedule."""
        self._check_manager()
        self.write({"active": True})
        return self._notify(_("Planification démarrée. Prochaine exécution automatique : %s.") % ", ".join(
            tools.format_datetime(self.env, plan.next_run_date, dt_format="short")
            for plan in self if plan.next_run_date
        ), "success")

    def action_stop(self):
        """Disable automatic runs; a run already in progress finishes normally."""
        self._check_manager()
        running = self.filtered(lambda plan: plan.execution_state == "running")
        self.write({"active": False})
        if running:
            return self._notify(_(
                "Planification arrêtée. L'exécution en cours se termine normalement, "
                "aucune nouvelle exécution automatique ne sera lancée."
            ), "warning")
        return self._notify(_("Planification arrêtée : plus aucune exécution automatique."), "warning")

    def action_refresh(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}


class PrimetechDatabaseCloneRunWizard(models.TransientModel):
    _name = "primetech.database.clone.run.wizard"
    _description = "Assistant d'exécution manuelle"

    plan_id = fields.Many2one("primetech.database.clone.plan", string="Planification", required=True, readonly=True)
    do_backup = fields.Boolean(
        string="Enregistrer une sauvegarde",
        help="Enregistre une archive de la base de production dans le dossier des sauvegardes.",
    )
    do_clone = fields.Boolean(
        string="Remplacer la base de test",
        help="Duplique la base de production en cours pour remplacer la base de test.",
    )
    test_database = fields.Char(related="plan_id.test_database", string="Base de test")
    backup_path = fields.Char(related="plan_id.backup_path", string="Dossier des sauvegardes")
    retention_count = fields.Integer(related="plan_id.retention_count", string="Sauvegardes conservées")
    destination = fields.Selection(related="plan_id.destination")
    sftp_host = fields.Char(related="plan_id.sftp_host")
    sftp_path = fields.Char(related="plan_id.sftp_path")

    def action_launch(self):
        self.ensure_one()
        if not (self.do_backup or self.do_clone):
            raise UserError(_("Cochez au moins une action : enregistrer une sauvegarde ou remplacer la base de test."))
        return self.plan_id._launch_manual(self.do_backup, self.do_clone)
