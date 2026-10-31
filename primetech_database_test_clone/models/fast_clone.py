# -*- coding: utf-8 -*-
"""Fast backup / clone pipeline and SFTP transfer helpers.

The production database is dumped once with ``pg_dump`` in directory format
using several parallel jobs. This single dump then feeds, at the same time:

* the test database, restored with parallel ``pg_restore`` jobs, its filestore
  being copied directly (no zip / unzip round trip);
* the backup archive, written in the standard Odoo format (``dump.sql``,
  ``filestore/``, ``manifest.json``) so it can still be restored from the Odoo
  database manager.
"""

import base64
import json
import logging
import os
import posixpath
import shutil
import stat
import subprocess
import uuid
import zipfile
from contextlib import closing

import odoo
from odoo import fields
from odoo.modules.neutralize import neutralize_database
from odoo.service import db as db_service
from odoo.tools.misc import exec_pg_environ, find_pg_tool

_logger = logging.getLogger(__name__)

COPY_BUFFER = 1024 * 1024


def _run_pg(tool, args, pg_options=None):
    env = exec_pg_environ()
    if pg_options:
        env["PGOPTIONS"] = pg_options
    result = subprocess.run(
        [find_pg_tool(tool), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise Exception("%s a échoué : %s" % (tool, (result.stderr or "").strip()[-2000:]))
    return result


def dump_directory(database, target_dir, jobs):
    """Dump ``database`` in pg_dump directory format with parallel jobs."""
    _run_pg("pg_dump", [
        "--no-owner", "--format=directory", "--jobs=%s" % jobs, "--compress=1",
        "--file=%s" % target_dir, database,
    ])


def restore_test_database(source, target, dump_dir, jobs, neutralize=True):
    """Replace ``target`` by the content of ``dump_dir`` and ``source``'s filestore."""
    if db_service.exp_db_exist(target):
        db_service.exp_drop(target)
    db_service._create_empty_database(target)
    # The test database is disposable: no synchronous commit, and more memory
    # for index creation, which is the longest part of the restoration.
    _run_pg(
        "pg_restore", ["--no-owner", "--jobs=%s" % jobs, "--dbname=%s" % target, dump_dir],
        pg_options="-c synchronous_commit=off -c maintenance_work_mem=512MB",
    )

    with closing(odoo.sql_db.db_connect(target).cursor()) as cr:
        # Same as ir.config_parameter.init(force=True) done by Odoo for a copy:
        # a new database identity, so the copy is never mistaken for production.
        params = {
            "database.secret": str(uuid.uuid4()),
            "database.uuid": str(uuid.uuid1()),
            "database.create_date": fields.Datetime.to_string(fields.Datetime.now()),
            "web.base.url": "http://localhost:%s" % odoo.tools.config.get("http_port"),
        }
        for key, value in params.items():
            cr.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", (value, key))
            if not cr.rowcount:
                cr.execute(
                    "INSERT INTO ir_config_parameter (key, value, create_date, write_date, create_uid, write_uid)"
                    " VALUES (%s, %s, now() at time zone 'UTC', now() at time zone 'UTC', 1, 1)",
                    (key, value),
                )
        if neutralize:
            neutralize_database(cr)
        cr.commit()

    source_fs = odoo.tools.config.filestore(source)
    target_fs = odoo.tools.config.filestore(target)
    if os.path.exists(target_fs):
        shutil.rmtree(target_fs)
    if os.path.exists(source_fs):
        shutil.copytree(source_fs, target_fs)


def build_odoo_archive(source, dump_dir, zip_path):
    """Write a standard Odoo backup zip from the directory dump."""
    with closing(odoo.sql_db.db_connect(source).cursor()) as cr:
        manifest = db_service.dump_db_manifest(cr)
    filestore = odoo.tools.config.filestore(source)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        with archive.open("dump.sql", "w", force_zip64=True) as sql_entry:
            process = subprocess.Popen(
                [find_pg_tool("pg_restore"), "--no-owner", "--file=-", dump_dir],
                env=exec_pg_environ(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            shutil.copyfileobj(process.stdout, sql_entry, COPY_BUFFER)
            stderr = process.stderr.read().decode(errors="replace")
            if process.wait() != 0:
                raise Exception("pg_restore a échoué : %s" % stderr.strip()[-2000:])
        archive.writestr("manifest.json", json.dumps(manifest, indent=4))
        if os.path.exists(filestore):
            for root, _dirs, files in os.walk(filestore):
                for name in files:
                    path = os.path.join(root, name)
                    relative = os.path.relpath(path, filestore).replace(os.sep, "/")
                    archive.write(path, "filestore/" + relative)


# --------------------------------------------------------------------------
# SFTP
# --------------------------------------------------------------------------

class RemoteAccessError(Exception):
    """Connected, but the remote account may not use the requested folder."""


class Sftp:
    """SFTP connection to the remote backup host (password authentication).

    The server key is recorded at the first connection and then verified on
    every connection, to detect a host substitution.
    """

    def __init__(self, host, port, user, password, known_key=False, timeout=30):
        import paramiko

        self.paramiko = paramiko
        self.user = user
        self.target_dir = False
        self.host_key = known_key
        self.new_host_key = False
        self.client = paramiko.SSHClient()
        if known_key:
            key_type, key_data = known_key.split(" ", 1)
            key = paramiko.PKey.from_type_string(key_type, base64.b64decode(key_data))
            hostname = host if int(port) == 22 else "[%s]:%s" % (host, port)
            self.client.get_host_keys().add(hostname, key_type, key)
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.client.connect(
                host, port=int(port), username=user, password=password, timeout=timeout,
                banner_timeout=timeout, auth_timeout=timeout, look_for_keys=False, allow_agent=False,
            )
        except paramiko.BadHostKeyException as exc:
            raise Exception(
                "La clé du serveur %s a changé : connexion refusée par sécurité. Si le serveur a "
                "réellement été réinstallé, effacez la clé enregistrée sur la planification." % host
            ) from exc
        except paramiko.SSHException as exc:
            if known_key and "not found in known_hosts" in str(exc):
                raise Exception("Clé du serveur %s inconnue : connexion refusée." % host) from exc
            raise
        transport = self.client.get_transport()
        server_key = transport.get_remote_server_key()
        if not known_key:
            self.host_key = "%s %s" % (server_key.get_name(), server_key.get_base64())
            self.new_host_key = True
        # Large window / packets: much faster transfers than paramiko defaults.
        self.sftp = paramiko.SFTPClient.from_transport(
            transport, window_size=2 ** 27, max_packet_size=32768
        )

    def close(self):
        try:
            self.sftp.close()
        finally:
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def home(self):
        try:
            return self.sftp.normalize(".")
        except OSError:
            return False

    def permission_error(self, action, path):
        """Explain a remote permission refusal and how to fix it."""
        home = self.home()
        message = (
            "Connexion et mot de passe corrects, mais le compte « %(user)s » n'a pas le droit %(action)s "
            "« %(path)s » sur l'ordinateur distant.\n"
            "Solution 1 – sur l'ordinateur distant, donnez ce droit au compte, par exemple :\n"
            "    sudo mkdir -p %(dir)s && sudo chown %(user)s: %(dir)s\n"
        ) % {"user": self.user, "action": action, "path": path, "dir": self.target_dir or path}
        if home:
            message += (
                "Solution 2 – choisissez un dossier appartenant au compte, par exemple « %s »."
            ) % posixpath.join(home, "sauvegardes_odoo")
        return RemoteAccessError(message)

    def makedirs(self, path):
        self.target_dir = path
        try:
            if stat.S_ISDIR(self.sftp.stat(path).st_mode):
                return
            raise RemoteAccessError("« %s » existe sur l'ordinateur distant mais n'est pas un dossier." % path)
        except FileNotFoundError:
            pass
        except PermissionError as exc:
            raise self.permission_error("d'accéder au dossier", path) from exc
        current = "/" if path.startswith("/") else ""
        for part in [p for p in path.split("/") if p]:
            current = posixpath.join(current, part) if current else part
            try:
                if not stat.S_ISDIR(self.sftp.stat(current).st_mode):
                    raise RemoteAccessError("« %s » existe sur l'ordinateur distant mais n'est pas un dossier." % current)
                continue
            except FileNotFoundError:
                pass
            except PermissionError:
                # A parent we may not inspect: try to create the next level anyway.
                continue
            try:
                self.sftp.mkdir(current)
            except PermissionError as exc:
                raise self.permission_error("de créer le dossier", current) from exc

    def check_writable(self, remote_dir):
        test_path = posixpath.join(remote_dir, ".primetech_test_ecriture")
        try:
            with self.sftp.open(test_path, "w") as test_file:
                test_file.write(b"ok")
            self.sftp.remove(test_path)
        except PermissionError as exc:
            raise self.permission_error("d'écrire dans le dossier", remote_dir) from exc

    def upload(self, local_path, remote_dir):
        self.makedirs(remote_dir)
        remote_path = posixpath.join(remote_dir, os.path.basename(local_path))
        partial = remote_path + ".part"
        try:
            with open(local_path, "rb") as source:
                self.sftp.putfo(source, partial, file_size=os.path.getsize(local_path), confirm=True)
        except PermissionError as exc:
            raise self.permission_error("d'écrire dans le dossier", remote_dir) from exc
        try:
            self.sftp.remove(remote_path)
        except FileNotFoundError:
            pass
        self.sftp.rename(partial, remote_path)
        return remote_path

    def listdir(self, remote_dir):
        try:
            return self.sftp.listdir(remote_dir)
        except FileNotFoundError:
            return []

    def remove(self, remote_path):
        self.sftp.remove(remote_path)
