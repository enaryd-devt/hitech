# Demandes de réapprovisionnement interne PrimeTech

Module Odoo 18 Community pour gérer les demandes de réapprovisionnement interne, l'allocation automatique du stock, la génération des transferts internes, leur coût logistique et le suivi opérationnel.

## Fonctionnalités principales

- Workflow : Brouillon, À approuver, Approuvée et Annulée.
- Recherche du stock disponible dans les emplacements internes hors destination.
- Allocations multi-emplacements par ligne.
- Transferts internes regroupés par source, avec validation automatique configurable.
- Répartition facultative du coût logistique par quantité, volume, poids ou parts égales.
- Tableau de bord, vues liste/kanban/activité, rapport PDF, code-barres et signatures.
- Chatter, e-mails, activités, pièces jointes et historique.
- Groupes Utilisateur, Responsable et Magasinier avec périmètre par entrepôt.

## Installation

1. Copier `primetech_replenishment_request` dans un répertoire de l'`addons_path` sans renommer le dossier.
2. Redémarrer Odoo.
3. En mode développeur, mettre à jour la liste des applications.
4. Rechercher **Demandes de réapprovisionnement interne PrimeTech** et l'installer.
5. Attribuer les groupes Réapprovisionnement aux utilisateurs.
6. Configurer la destination par défaut et la validation automatique depuis le menu Configuration du module.

Dépendances installées par Odoo : `base`, `mail`, `stock`, `stock_account`, `product` et `web`.

Pour une mise à jour, sauvegarder la base, remplacer les sources, redémarrer Odoo puis exécuter :

```bash
odoo-bin -d NOM_BASE -u primetech_replenishment_request --stop-after-init
```

Toujours tester l'installation ou la mise à niveau sur une copie de la base avant la production.

## Configuration et sécurité

- **Destination par défaut** : emplacement interne proposé lors de la création.
- **Validation automatique** : si active, l'approbation renseigne les quantités faites et valide les transferts; sinon, ils restent à traiter dans Inventaire.
- **Utilisateur** : crée et soumet ses demandes.
- **Responsable** : approuve et peut remettre une demande soumise ou annulée en brouillon.
- **Magasinier** : consulte son périmètre et peut approuver/transférer, sans droit de retour en brouillon.
- **Administrateur** : configure le module et ses accès.

Le retour en brouillon est bloqué dès qu'un transfert est lié à la demande, afin de préserver la cohérence entre document et mouvements de stock.

## Utilisation

1. Créer une demande et sélectionner la destination.
2. Ajouter produits, quantités, conditionnements et, si besoin, une source.
3. Contrôler les disponibilités et corriger toute ligne partielle ou indisponible.
4. Saisir facultativement un coût de transfert positif et sa méthode de répartition.
5. Soumettre : la demande devient non modifiable et une activité est créée pour les responsables.
6. Si nécessaire, un responsable la remet en brouillon, la corrige et la soumet à nouveau.
7. Approuver : les transferts internes sont créés par emplacement source puis validés selon la configuration.
8. Suivre les transferts, l'historique, les pièces jointes, le tableau de bord et le rapport PDF.
9. En cas d'annulation, saisir un motif qui sera publié dans le chatter.

## Impact sur les modules existants

- **Inventaire** : crée de vrais transferts et mouvements internes. Avec l'auto-validation, les quantités disponibles sont déplacées immédiatement.
- **Comptabilité de stock** : un coût logistique facultatif produit des couches de valorisation après réalisation des transferts; faire valider son usage par l'équipe financière.
- **Produits** : réutilise unités, conditionnements, poids et volume sans remplacer les fiches existantes.
- **Discuss/Mail** : crée messages de suivi, activités et notifications.
- **Web** : ajoute ses propres menus, vues et tableau de bord sans remplacer les vues standard.

Le module ne crée ni achat, ni vente, ni fabrication et ne remplace pas les règles de réapprovisionnement standard d'Odoo.

## Exploitation et désinstallation

- Désactiver l'auto-validation si la préparation physique doit être confirmée séparément.
- Sauvegarder avant toute mise à jour ou désinstallation.
- La désinstallation supprime les modèles et données propres au module; les transferts déjà créés peuvent rester dans Inventaire.
- Après mise à niveau, vérifier droits, paramètres, vues et modèles d'e-mail sur une base de test.

La documentation détaillée visible dans **Apps &gt; Informations** se trouve dans `static/description/index.html`.
