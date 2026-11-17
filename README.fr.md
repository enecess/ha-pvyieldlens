[English](README.md) | [中文](README.zh-CN.md) | **Français** | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Comparez la puissance estimée et réelle de vos panneaux. Suivez le PR et l’énergie estimée pour la journée et au total.

## Fonctions

- Tableau de bord : puissance, PR et production clôturée du jour.
- Comparaisons d’efficacité sur les règlements originaux de 1, 5 ou 10 minutes.
- Énergie estimée du jour et depuis la configuration.
- Énergie quotidienne comparée sur 7/30 jours ou une période personnalisée de 90 dates maximum.
- Prévisions originales et corrigées par 15 minutes.
- Six langues, avec un menu en haut à droite.

## Démarrage rapide

### App Home Assistant

Pour Home Assistant OS.

[![Ajouter le dépôt d’apps PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Cliquez sur le bouton ci-dessus et confirmez **Ajouter** dans Home Assistant.
2. Trouvez **PVYieldLens** dans la boutique d’apps, puis installez et démarrez l’app.
3. Ouvrez la page Web, puis **Paramètres** pour choisir les capteurs et renseigner les panneaux.

Si le bouton n’ouvre pas Home Assistant, allez dans **Paramètres > Applications > Installer une application > menu en haut à droite > Dépôts** et ajoutez :

```text
https://github.com/enecess/ha-pvyieldlens#dev_v0
```

Pour les versions de Home Assistant antérieures à 2026.2, utilisez **Paramètres > Modules complémentaires > Boutique des modules complémentaires > menu en haut à droite > Dépôts**. L’app nécessite Home Assistant 2025.9.0 ou une version plus récente.

### Docker

Téléchargez ce dépôt et ouvrez son dossier. Créez le fichier de réglages :

```sh
cp .env.example .env
```

Dans `.env`, choisissez un mot de passe pour `PVYL_WEB_PASSWORD`, puis démarrez l’app :

```sh
docker compose up -d --build
```

Ouvrez [localhost:8099](http://localhost:8099). Connectez-vous avec `admin` et le mot de passe choisi. Pour la première connexion, saisissez l’adresse Home Assistant et un jeton d’accès de longue durée appartenant à un **administrateur** Home Assistant dans **Paramètres**, puis cliquez sur **Actualiser les capteurs**. Si l’adresse et le jeton sont déjà configurés, les capteurs se chargent automatiquement à la première ouverture des **Paramètres**. Utilisez **Actualiser les capteurs** après une modification de la connexion, pour mettre à jour la liste ou pour réessayer après un échec. Les droits d’administration sont nécessaires pour publier les capteurs de sortie.

Par défaut, la page est accessible sur la machine Docker. Pour y accéder depuis un autre appareil, remplacez `127.0.0.1:8099:8099` par `8099:8099` dans `compose.yaml`.

## Réglages

Le **Tableau de bord** présente la puissance actuelle et la production du jour ; **Efficacité** compare l’énergie clôturée et le PR ; **Prévisions** compare les valeurs originales et corrigées. Les **Paramètres** restent en haut à droite et les trois vues restent accessibles. Le répertoire couvre la connexion HA, les modules, les capteurs, la surveillance et les prévisions.

**Enregistrer la configuration** vous laisse dans les Paramètres. **Abandonner les modifications** recharge la configuration enregistrée sur le serveur et remplace vos modifications ; en cas d’échec, le brouillon est conservé pour réessayer. Quitter avec des modifications demande de poursuivre l’édition ou de les abandonner. Revenir aux Paramètres recharge la configuration enregistrée.

Le menu **Mode du thème**, en haut à droite, propose Auto, Clair et Sombre. Auto suit le mode de Home Assistant dans son interface et la préférence système si son contexte est inaccessible. Clair ou Sombre impose un choix local ; Auto rétablit le suivi. Changer de langue ou de thème conserve le brouillon.

| Réglage | Valeur à saisir |
| --- | --- |
| Puissance maximale totale aux STC | Somme des puissances maximales des modules aux conditions de test standard (STC) en W, par exemple `5000`. |
| Coefficient de température de Pmax | Coefficient Pmax de la fiche du module en %/°C, par exemple `-0,35`. |
| Puissance réelle | Capteur de production solaire (W ou kW). |
| Température des modules | Capteur de température des panneaux (°C, °F ou K). |
| Irradiance | Capteur dans le même plan que les panneaux (W/m² ou kW/m²). |
| Intervalle de règlement | 1, 5 ou 10 minutes. Par défaut : 5 minutes. |
| Moyenne sur | Durée utilisée pour la moyenne en direct. Par défaut : 60 secondes. |
| Mise à jour toutes les | Délai entre deux mises à jour. Par défaut : 5 secondes. |

Enregistrez, puis ouvrez **Tableau de bord**. Le premier résultat clôturé apparaît dans **Efficacité** à la fin de la période en cours. Sous **Délai sans données**, réglez le temps d’attente pour chaque capteur.

Le Tableau de bord précharge les dix dernières minutes à l’ouverture ou à la reconnexion. Les données de production montrent aujourd’hui les puissances estimée/réelle clôturées, l’irradiance et la température des modules. Le graphique d’énergie propose 7 jours par défaut, 30 jours ou une période personnalisée inclusive de 90 dates du foyer au maximum, sans dépasser aujourd’hui. Une absence reste vide et zéro reste zéro ; les règlements et cumuls conservés ne changent pas.

Efficacité montre le PR de la période, sa variation en points par rapport à la période précédente comparable et l’énergie estimée moins l’énergie réelle. Aujourd’hui se compare à hier jusqu’à la même heure locale ; 24 heures aux 24 heures précédentes ; 7/30 jours au même intervalle décalé de 7/30 dates du foyer. Les deux graphiques partagent le choix du résumé quotidien ou de chaque intervalle de règlement configuré.

Le lissage concerne seulement le dessin. Souris, toucher et clavier inspectent les enregistrements originaux, y compris les intervalles de prévision de 15 minutes. Énergie et PR utilisent les valeurs non lissées. Les dates et prévisions suivent l’heure du foyer ; les horodatages de surveillance et de récupération suivent la préférence HA server/local du lecteur, ou le navigateur sous Docker autonome. Les décalages UTC distinguent au besoin les heures répétées.

## Prévisions de production

Les prévisions sont désactivées par défaut à la première installation. Dans **Paramètres > Prévisions**, activez-les et indiquez l’inclinaison (0–90°), l’orientation (nord 0°, est 90°, sud 180°, ouest 270°, ou un azimut personnalisé de 0° à moins de 360°) et le NOCT de la fiche technique (plus de 20°C, au maximum 80°C ; 45°C par défaut). La puissance maximale totale aux STC et le coefficient de température de Pmax sont partagés avec la surveillance. Le lieu et le fuseau sont lus automatiquement depuis la connexion Home Assistant enregistrée ; modifiez-les dans HA.

La surveillance utilise la **Température des modules** mesurée. Les prévisions utilisent la **Température de l’air** et la **Température nominale de fonctionnement des cellules (NOCT)** pour calculer la **Température estimée des cellules**. Ces grandeurs sont distinctes ; la surveillance ne convertit pas la température des modules en température des cellules.

Open-Meteo fournit des entrées de modèle toutes les 15 minutes pour aujourd’hui et les six jours calendaires suivants du foyer. Certaines régions ou variables interpolent des modèles horaires ; ce pas ne garantit pas une meilleure précision. Choisissez une date pour les énergies originale/corrigée, les courbes de puissance et les détails. Le jour couvre toute la journée ; **Reste aujourd’hui** va de maintenant à minuit du foyer et diminue entre téléchargements. Un jour normal comporte 96 intervalles, contre 92 ou 100 lors d’un changement d’heure.

Les cartes conservent la météo et les températures maximale/minimale des prévisions horaires, avec deux barres d’énergie et les kWh. Le repère chaud **Aujourd’hui** suit minuit du foyer indépendamment de la sélection bleue. Les résumés météo gardent les échantillons horaires de la même requête, du même cache et de la même heure de récupération. Météo et énergie peuvent être indisponibles séparément ; zéro reste valide.

La météo s’actualise normalement chaque heure ou avec **Actualiser les prévisions**. Le cache correspondant survit au redémarrage. Un échec conserve l’heure de récupération, affiche l’erreur et réessaie après 15 minutes. Des entrées manquantes rendent les totaux concernés indisponibles (**—**). Les états désactivé, lieu absent, chargement et absence de données restent affichés.

La **Prévision originale** garde le modèle météo/NOCT ; la **Prévision corrigée** le multiplie par le PR récent pondéré par l’énergie et la récence des dates terminées du foyer. Dans **Paramètres > Prévisions**, les jours historiques du PR valent n=14 par défaut, entier de 3 à 90 ; la demi-vie vaut n/2 jours. Il faut au moins 3 dates admissibles à énergie estimée positive. Les énergies réelle et estimée couvrent les mêmes périodes valides après la dernière configuration de surveillance comparable. Une production réelle nulle reste admissible ; un PR supérieur à 100 % n’est pas plafonné. Sans assez d’historique, les valeurs corrigées affichent **—**, les originales restent disponibles. Modifier n recalcule la correction sans nouvelle requête météo.

La correction concerne seulement la page et l’API applicative. Les 13 identifiants et significations des sorties HA restent inchangés ; les quatre entités de prévision gardent l’énergie originale intégrée à partir des intervalles de 15 minutes.

Il s’agit d’une référence estimée en courant continu pour un seul champ de panneaux, avec irradiance dans leur plan et modèle thermique NOCT simplifié. Rendement/écrêtage de l’onduleur, ombrage, neige, salissures et pertes ne sont pas modélisés ; la production réelle en courant alternatif n’est pas garantie. Les quatre entités météo sont en kWh, de classe energy, sans `state_class` ; elles peuvent diminuer et restent séparées des compteurs cumulés. Elles ne fournissent pas d’intégration native aux prévisions HA ni au tableau de bord Énergie.

## Capteurs de sortie

| Indicateur | Nom de l’entité HA | Unité |
| --- | --- | --- |
| Puissance estimée clôturée | `settled_estimated_power` | W |
| Puissance réelle clôturée | `settled_actual_power` | W |
| PR clôturé | `settled_pr` | % |
| Énergie estimée aujourd’hui | `estimated_energy_today` | kWh |
| Énergie estimée cumulée | `estimated_energy_lifetime` | kWh |
| Puissance estimée en direct | `live_estimated_power` | W |
| Puissance réelle en direct | `live_actual_power` | W |
| PR en direct | `live_pr` | % |
| Puissance optimisable en direct | `live_optimizable_power` | W |
| Énergie prévue aujourd’hui | `forecast_energy_today` | kWh |
| Énergie prévue restante aujourd’hui | `forecast_energy_remaining_today` | kWh |
| Énergie prévue demain | `forecast_energy_tomorrow` | kWh |
| Énergie prévue sur 7 jours | `forecast_energy_7d` | kWh |

Le nom de l’entité HA est son nom d’affichage. L’identifiant complet est `sensor.pvyieldlens_` suivi de ce nom ; par exemple, `sensor.pvyieldlens_settled_estimated_power`.

## Formule du PR

La puissance estimée tient compte de la puissance maximale totale aux STC, de la température des modules et de l’irradiance :

```text
P_estimated = P_stc × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_estimated × 100%
```

`P_stc` : puissance maximale totale aux STC (W) ; `K` : coefficient de température de Pmax (%/°C), en pourcentage de la fiche technique, par exemple `-0,35` ; `T` : température des modules (°C) ; `G` : irradiance dans le plan des modules (W/m²). L’app divise K par 100 une seule fois.

Le ratio de performance (PR) compare la puissance réelle à la puissance estimée. La puissance optimisable est la puissance estimée moins la puissance réelle ; elle peut être négative.

## Comprendre les résultats

- Le PR peut dépasser 100 %. Il n’est pas affiché si la puissance estimée est nulle.
- Une puissance optimisable négative signifie que la puissance réelle dépasse la puissance estimée.
- L’énergie est comptée quand les trois capteurs ont des données. Les périodes manquantes sont exclues.
- L’énergie du jour revient à zéro à minuit, selon le fuseau de Home Assistant. Le total commence au premier réglage.

Après une interruption, certaines périodes peuvent rester sans données. Conservez les données de l’app lors d’une mise à jour ou d’une réinstallation. Pour l’app, utilisez les sauvegardes de Home Assistant ; avec Docker autonome, arrêtez le conteneur avant de copier le dossier `/data`.
