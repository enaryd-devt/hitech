## Module <primetech_biometric_attendance>

#### 11.11.2026
#### Version 18.0.4.0.0
##### ADD

- Application « Gestion des pointages » avec tableau de bord temps réel (présents,
  retards, absents, non arrivés, congés, pointages à corriger, tendance 14 jours,
  présence par département, retardataires du mois, état des pointeuses).
- Horaires de pointage (en-tête + jours) : heures prévues, pause, tolérance de
  retard (comptée depuis l'heure prévue ou au-delà de la tolérance), tolérance de
  départ anticipé, seuil d'heures supplémentaires, périodes de pointage
  autorisées. Affectation par employé, département (hérité des parents) ou
  horaire par défaut de la société ; à défaut, heures de travail Odoo.
- Journées de présence : arrivée, départ, heures travaillées, retard, départ
  anticipé, heures supplémentaires, absences, congés et jours fériés
  (resource.calendar.leaves), pointages incomplets, justification RH, ajout de
  pointage manuel, calendrier, analyse pivot / graphique.
- Rapport PDF de présence (synthèse + détail jour par jour) et assistant de recalcul.
- Administration des pointeuses : fuseau horaire propre à l'appareil, clé de
  communication, informations matérielles (série, firmware, capacités, mémoire,
  écart d'horloge), import des utilisateurs de l'appareil, journal de
  synchronisation, vidage de la mémoire sans perte dans Odoo, réimport.
- Passerelle locale (Odoo hébergé sur un VPS) : mode de connexion « Passerelle »
  par pointeuse, clé d'API, route `/primetech_biometric/relay/hello|push`,
  programme Windows `relay/dist/primetech_zk_relay.exe` (source
  `relay/primetech_zk_relay.py`, construit avec PyInstaller) installé en tâche
  planifiée au démarrage du PC, paquet zip préconfiguré téléchargeable depuis la
  fiche de la pointeuse. Les pointages faits PC éteints restent dans la
  pointeuse et sont envoyés avec leur heure réelle ; commandes à distance
  (heure, vidage de la mémoire après envoi, redémarrage).
- Passerelle 2.0 : console Web locale (http://localhost:47321, raccourci
  « Pointeuse PrimeTech » sur le Bureau) ; association par code temporaire
  généré dans Odoo (onglet Passerelle, bascule automatique en mode passerelle) ;
  adresse du serveur par nom de domaine ou IP:port avec détection d'Odoo et des
  bases ; recherche automatique des pointeuses sur le réseau local ; plusieurs
  pointeuses par passerelle ; PIN administrateur ; protections contre les
  requêtes d'autres sites. Routes serveur `ping` et `pair`.
- Paramètres (Présences > Configuration) : interprétation des pointages
  (premier/dernier, paires, sens envoyé par l'appareil), anti-doublon,
  génération des présences Odoo, conservation du journal.

##### FIX

- Les pointages étaient convertis avec le fuseau de l'utilisateur qui
  synchronisait (OdooBot = GMT pour la tâche planifiée) : doublons décalés
  d'une heure. La migration supprime les pointages enregistrés « dans le futur ».
- Les pointages sans sens (255), cas des pointeuses HITECH, ne généraient ni
  présence ni retard.
- `zk.machine.attendance` n'hérite plus de `hr.attendance` (recalculs d'heures
  supplémentaires et suivi de messages parasites à chaque pointage importé).
- « Effacer les pointages » supprimait tous les pointages Odoo de toutes les
  pointeuses ; la pointeuse était laissée verrouillée après téléchargement.
- Droits : tout utilisateur interne pouvait modifier ou supprimer pointeuses et
  pointages. Administration réservée aux administrateurs Présences.
- Les identifiants inconnus ne créent plus d'employé automatiquement (option par
  pointeuse) ; ils sont signalés et importés dès qu'ils sont associés.

#### 30.03.2026
#### Version 18.0.1.0.0
##### ADD

- Initial commit for Biometric Device Integration
