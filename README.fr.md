[English](README.md) | [中文](README.zh-CN.md) | **Français** | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

Comparez la puissance prévue et réelle de vos panneaux. Suivez le PR et l’énergie prévue pour la journée et au total.

## Fonctions

- Puissance, PR et écart de puissance en direct.
- Historique de puissance et de PR par périodes de 1, 5 ou 10 minutes.
- Énergie prévue pour aujourd’hui et depuis la mise en service.
- Courbes sur 24 heures, 7 jours ou 30 jours.
- Six langues, à choisir dans le menu en haut à droite.

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

**Temps réel** affiche les moyennes actuelles et les diagnostics ; **Historique**, les périodes clôturées et l’énergie/PR de la plage choisie ; **Prévisions**, les estimations météo. Les totaux du jour et depuis l’installation restent indépendants de cette plage. L’entrée **Paramètres**, avec roue dentée et texte, est séparée en haut à droite ; les trois onglets de données restent accessibles. Le répertoire fait défiler un formulaire continu : Connexion Home Assistant, Panneaux solaires, Capteurs, Surveillance et Prévisions.

**Enregistrer** vous laisse dans les Paramètres. **Annuler** recharge la configuration enregistrée sur le serveur et remplace vos modifications ; en cas d’échec, le brouillon est conservé pour réessayer. Quitter avec des modifications demande de poursuivre l’édition ou de les abandonner. Revenir aux Paramètres recharge la configuration enregistrée.

Le menu **Mode du thème**, en haut à droite, propose Auto, Clair et Sombre. Auto suit le mode de Home Assistant dans son interface et la préférence système si son contexte est inaccessible. Clair ou Sombre impose un choix local ; Auto rétablit le suivi. Changer de langue ou de thème conserve le brouillon.

| Réglage | Valeur à saisir |
| --- | --- |
| Puissance nominale totale | Somme des puissances des panneaux en W, par exemple `5000`. |
| Coefficient de température K | Valeur de la fiche du panneau en %/°C, par exemple `-0,35`. |
| Puissance | Capteur de production solaire (W ou kW). |
| Température des panneaux | Capteur de température des panneaux (°C, °F ou K). |
| Rayonnement solaire | Capteur dans le même plan que les panneaux (W/m² ou kW/m²). |
| Intervalle de l’historique | 1, 5 ou 10 minutes. Par défaut : 5 minutes. |
| Moyenne sur | Durée utilisée pour la moyenne en direct. Par défaut : 60 secondes. |
| Mise à jour toutes les | Délai entre deux mises à jour. Par défaut : 5 secondes. |

Enregistrez, puis ouvrez **Temps réel**. Le premier résultat clôturé apparaît dans **Historique** à la fin de la période en cours. Sous **Délai sans données**, réglez le temps d’attente pour chaque capteur.

Le direct précharge une fenêtre fixe de dix minutes à l’ouverture ou à la reconnexion. Chaque point utilise toujours **Moyenne sur** et la collecte suit **Mise à jour toutes les**. La tendance est reconstruite à partir des observations conservées et des paramètres actuels ; ce n’est pas un journal des instantanés publiés. Les observations absentes ou expirées et le point actuellement hors ligne restent des lacunes. Les anciennes coupures sans lacune identifiable ne peuvent pas être reconstituées précisément. L’Historique conserve les résultats clôturés originaux. L’âge des sources avance localement chaque seconde, sans requête supplémentaire aux capteurs.

Les courbes lissées servent uniquement à l’affichage. Les infobulles à la souris, au toucher et au clavier donnent les valeurs originales ; les prévisions donnent l’intervalle horaire original. Énergie et PR utilisent les données originales. L’heure du domicile détermine les totaux journaliers, dates de prévision, météo, Aujourd’hui et intervalles horaires. Les horodatages du direct/de l’historique et les heures de mise à jour/récupération suivent la préférence HA server/local du lecteur ; Docker autonome utilise l’heure du navigateur. Une préférence HA illisible entraîne un repli sur l’heure du domicile. Une note signale les fuseaux différents ; les décalages UTC ne servent qu’à distinguer les heures répétées ou un changement de décalage dans un intervalle.

## Prévisions de production

Les prévisions sont désactivées par défaut, y compris après une mise à jour. Dans **Paramètres > Prévisions**, activez-les et indiquez l’inclinaison (0–90°), l’orientation (nord 0°, est 90°, sud 180°, ouest 270°, ou un azimut personnalisé de 0° à moins de 360°) et le NOCT de la fiche technique (plus de 20°C, au maximum 80°C ; 45°C par défaut). La puissance nominale et K sont partagés avec la surveillance. Le lieu et le fuseau sont lus automatiquement depuis la connexion Home Assistant enregistrée ; modifiez-les dans HA.

Open-Meteo fournit la météo horaire pour aujourd’hui et les six jours calendaires locaux suivants. Choisissez une date pour l’énergie de la journée, la courbe horaire et le tableau des intervalles. La prévision du jour couvre toute la journée ; **Reste aujourd’hui** couvre seulement maintenant jusqu’à minuit local. Ces valeurs utilisent la dernière météo obtenue avec succès et sont distinctes de l’énergie théorique clôturée calculée à partir des capteurs. L’énergie restante diminue avec le temps entre deux téléchargements ; une nouvelle météo peut aussi réviser le total du jour.

Chaque carte présente météo, maximum/minimum des prévisions horaires, barre d’énergie et kWh. Le libellé chaud **Aujourd’hui** suit minuit au domicile et reste visible lorsqu’une autre date est sélectionnée en bleu. Les températures sont les extrêmes des relevés horaires bruts ; la météo représentative utilise le code WMO connu maximal du jour. Chaque champ exige tous les échantillons horaires UTC attendus dans la journée du domicile, y compris les journées de 23/25 heures et les fuseaux fractionnaires. Un champ incomplet est indisponible, l’autre reste visible s’il est complet. Zéro est valide ; une météo inconnue reçoit une icône neutre. Météo et puissance partagent requête, cache et heure de récupération, sans cadence supplémentaire. Les anciens caches conservent l’énergie valide et obtiennent la météo au prochain rafraîchissement normal.

La météo est actualisée chaque heure, ou avec **Actualiser les prévisions**. Le cache correspondant est conservé au redémarrage. Un échec conserve l’heure d’origine et signale des données anciennes ; nouvelle tentative après 15 minutes. Les données datant d’au moins deux heures sont également anciennes. Des intervalles manquants rendent les totaux concernés indisponibles ; la complétude reste affichée et les valeurs manquantes ne deviennent pas zéro. L’interface distingue désactivation, lieu HA absent, chargement initial et indisponibilité.

Il s’agit d’une référence théorique en courant continu pour un seul champ de panneaux, avec rayonnement dans leur plan et modèle thermique NOCT simplifié. Rendement/écrêtage de l’onduleur, ombrage, neige, salissures et pertes ne sont pas modélisés ; la production réelle en courant alternatif n’est pas garantie. Les quatre entités météo sont en kWh, de classe energy, sans `state_class` ; elles peuvent diminuer et restent séparées des compteurs cumulés. Elles ne fournissent pas d’intégration native aux prévisions HA ni au tableau de bord Énergie.

## Capteurs de sortie

| Résultat | ID de l’entité | Unité |
| --- | --- | --- |
| Puissance prévue | `sensor.pvyieldlens_estimated_power` | W |
| Puissance réelle | `sensor.pvyieldlens_actual_power` | W |
| PR | `sensor.pvyieldlens_pr` | % |
| Énergie prévue aujourd’hui | `sensor.pvyieldlens_daily_estimated_energy` | kWh |
| Énergie prévue au total | `sensor.pvyieldlens_total_estimated_energy` | kWh |
| Puissance prévue en direct | `sensor.pvyieldlens_realtime_estimated_power` | W |
| Puissance réelle en direct | `sensor.pvyieldlens_realtime_actual_power` | W |
| PR en direct | `sensor.pvyieldlens_realtime_pr` | % |
| Écart de puissance en direct | `sensor.pvyieldlens_realtime_optimizable_power` | W |
| Prévision aujourd’hui | `sensor.pvyieldlens_forecast_energy_today` | kWh |
| Prévision restante aujourd’hui | `sensor.pvyieldlens_forecast_energy_remaining_today` | kWh |
| Prévision demain | `sensor.pvyieldlens_forecast_energy_tomorrow` | kWh |
| Prévision sur 7 jours | `sensor.pvyieldlens_forecast_energy_7d` | kWh |

## Formule du PR

La puissance prévue tient compte de la puissance nominale, de la température et du soleil :

```text
P_expected = P_rated × [1 + (K / 100) × (T − 25)] × G / 1000
PR = P_actual / P_expected × 100%
```

`P_rated` : puissance nominale (W) ; `K` : coefficient de température (%/°C) ; `T` : température des panneaux (°C) ; `G` : rayonnement reçu par les panneaux (W/m²).

Le PR compare la puissance réelle à la puissance prévue. L’écart est la puissance prévue moins la puissance réelle.

## Comprendre les résultats

- Le PR peut dépasser 100 %. Il n’est pas affiché si la puissance prévue est nulle.
- Un écart négatif signifie que la puissance réelle dépasse la puissance prévue.
- L’énergie est comptée quand les trois capteurs ont des données. Les périodes manquantes sont exclues.
- L’énergie du jour revient à zéro à minuit, selon le fuseau de Home Assistant. Le total commence au premier réglage.

Après une interruption, certaines périodes peuvent rester sans données. Conservez les données de l’app lors d’une mise à jour ou d’une réinstallation. Pour l’app, utilisez les sauvegardes de Home Assistant ; avec Docker autonome, arrêtez le conteneur avant de copier le dossier `/data`.
