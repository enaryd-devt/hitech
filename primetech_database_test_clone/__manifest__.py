# -*- coding: utf-8 -*-
{
    "name": "Primetech - Sauvegarde et base de test",
    "summary": "Sauvegarde planifiée et copie sécurisée de la base de production",
    "version": "18.0.1.5.0",
    "description": """
        <h2>Manuel d'utilisation</h2>
        <ol>
            <li>Ouvrez <strong>Sauvegarde et test</strong> puis cliquez sur <strong>Nouveau</strong>.</li>
            <li>Cochez les actions des exécutions automatiques : <strong>Enregistrer une sauvegarde</strong> et/ou <strong>Remplacer la base de test</strong>. Indiquez le dossier de sauvegarde, la base de test et le <strong>nombre de sauvegardes conservées</strong> (0 = tout conserver) : après chaque nouvelle sauvegarde, les plus anciennes sont supprimées.</li>
            <li>Choisissez la fréquence (chaque jour, semaine ou mois), le jour et l'heure d'exécution, de préférence en dehors des heures de travail.</li>
            <li>Enregistrez : la planification est <strong>En cours</strong> et attend sa <strong>prochaine exécution</strong> automatique. Utilisez <strong>Arrêter la planification</strong> / <strong>Démarrer la planification</strong> pour la suspendre ou la reprendre.</li>
            <li>Utilisez <strong>Lancer manuellement</strong> pour une exécution immédiate, même si la planification est arrêtée : un assistant demande les actions à exécuter, puis l'exécution démarre aussitôt en arrière-plan (statut <em>En cours d'exécution</em>) et vous pouvez continuer à travailler. Le Journal distingue les exécutions manuelles et automatiques.</li>
            <li>Pour enregistrer les sauvegardes sur un <strong>ordinateur distant</strong> (par exemple un disque dur externe), choisissez la destination <strong>Ordinateur distant (SSH / SFTP)</strong>, renseignez l'adresse, l'utilisateur, le mot de passe et le dossier distant, puis cliquez sur <strong>Tester la connexion</strong>. La clé du serveur est enregistrée puis vérifiée à chaque envoi.</li>
            <li>Créez <strong>plusieurs planifications</strong> (bouton <strong>Dupliquer</strong>) pour envoyer les sauvegardes sur plusieurs ordinateurs par sécurité. Chaque planification a son propre dossier et son propre nombre de sauvegardes conservées ; une seule exécution a lieu à la fois, les autres attendent leur tour.</li>
            <li>Le champ <strong>Processus parallèles</strong> règle la vitesse d'exécution (4 par défaut).</li>
            <li>Le menu <strong>Configuration › Paramètres</strong> définit les valeurs proposées aux nouvelles planifications (dossier racine, base de test, heure, conservation, processus parallèles) et le délai de déblocage d'une exécution interrompue.</li>
            <li>Pendant une exécution, la fiche, la liste et le Journal se mettent à jour automatiquement à la fin, sans changer de vue.</li>
            <li>Consultez le menu <strong>Journal</strong> pour contrôler les résultats et les erreurs éventuelles.</li>
        </ol>
        <p><strong>Sécurité :</strong> la base cible est remplacée. La copie de test neutralise les actions sortantes, notamment les emails.</p>
    """,
    "category": "Administration",
    "author": "Primetech",
    "license": "LGPL-3",
    "depends": ["base_setup"],
    "data": [
        "security/primetech_database_test_clone_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/database_clone_log_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "primetech_database_test_clone/static/src/js/auto_refresh.js",
            "primetech_database_test_clone/static/src/xml/auto_refresh.xml",
        ],
    },
    "installable": True,
    "application": True,
}
