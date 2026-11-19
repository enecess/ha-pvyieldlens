[English](README.md) | [中文](README.zh-CN.md) | **Français** | [Deutsch](README.de.md) | [Polski](README.pl.md) | [Italiano](README.it.md)

# PVYieldLens

## Vue d’ensemble

PVYieldLens compare la production solaire mesurée à celle que votre installation photovoltaïque pourrait fournir dans les conditions observées. Suivez le ratio de performance (PR) dans Home Assistant et consultez les prévisions de production sur sept jours.

## Installation

### Home Assistant OS

L’application nécessite Home Assistant 2025.9.0 ou une version ultérieure.

[![Ajouter le dépôt d’apps PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens%23dev_v0)

1. Utilisez le bouton ci-dessus, puis confirmez avec **Ajouter** dans Home Assistant. Pour ajouter le dépôt manuellement, ouvrez **Paramètres > Applications > Installer une application > ⋮ > Dépôts** et saisissez `https://github.com/enecess/ha-pvyieldlens#dev_v0`.
2. Recherchez **PVYieldLens** dans le **Magasin d'applications** et sélectionnez **Installer**.
3. Sélectionnez **Démarrer**, puis **Ouvrir l'interface utilisateur web**.

Avant Home Assistant 2026.2, ouvrez **Paramètres > Modules complémentaires > Boutique des modules complémentaires**, puis ajoutez le dépôt depuis le menu ⋮.

### Docker

1. Téléchargez ce dépôt et ouvrez son dossier. Copiez `.env.example` vers `.env` et choisissez un mot de passe dans `PVYL_WEB_PASSWORD`.
2. Exécutez `docker compose up -d --build`.
3. Sur la machine qui héberge Docker, ouvrez [localhost:8099](http://localhost:8099). Connectez-vous avec le compte `admin` et le mot de passe choisi.

Pour accéder à l’application depuis un autre appareil, remplacez `127.0.0.1:8099:8099` par `8099:8099` dans `compose.yaml`.

## Configuration

Ouvrez les **Paramètres** de PVYieldLens. Le menu **Langue** en haut à droite permet de changer la langue de l’interface.

### Connexion Home Assistant

L’application Home Assistant se connecte automatiquement. Avec Docker, saisissez l’**Adresse Home Assistant** et un **Jeton d’accès de longue durée** d’un administrateur de Home Assistant, puis sélectionnez **Actualiser les entités**. Les droits d’administrateur sont nécessaires pour publier les capteurs de sortie.

Saisissez un jeton à la première configuration ou lors d’un changement d’adresse. Pour réutiliser le jeton enregistré avec la même adresse, laissez le champ vide.

### Modules photovoltaïques

| Paramètre | Valeur à saisir |
| --- | --- |
| **Puissance maximale totale aux STC** | Additionnez les puissances nominales en W. Dix modules de 500 W totalisent 5 000 W. |
| **Coefficient de température de Pmax** | Valeur de la fiche technique en %/°C, par exemple −0,35. |
| **Inclinaison des modules** | De 0° à 90°. |
| **Orientation des modules** | Azimut mesuré dans le sens horaire à partir du nord (0°), inférieur à 360°. Choisissez un point cardinal ou **Personnalisé**. |
| **Température nominale de fonctionnement des cellules (NOCT)** | Valeur de la fiche technique, supérieure à 20 °C et jusqu’à 80 °C. Par défaut, 45 °C. |

Choisissez **Valeur fixe** ou **Entité HA** séparément pour l’inclinaison et l’orientation. Sélectionnez une entité `sensor.*`, `number.*` ou `input_number.*` qui fournit un angle en degrés (°). Avec un suiveur solaire, chaque actualisation utilise les angles lus à cet instant pour l’ensemble des prévisions.

*L’installation Berlin Demo de 5 000 W est inclinée à 35° et orientée **Sud · 180°**.*

![Réglages des modules PV de Berlin Demo avec une puissance de 5 000 W, une inclinaison de 35° et une orientation sud](docs/images/settings-pv-modules.png)

### Capteurs

| Paramètre | Capteur et unités prises en charge |
| --- | --- |
| **Puissance réelle** | Puissance photovoltaïque en W ou kW. |
| **Irradiance** | Irradiance dans le plan des modules, en W/m² ou kW/m². |
| **Température des modules (facultative)** | Température en °C, °F ou K. Si le champ est vide, l’estimation utilise la température de l’air d’Open-Meteo, l’irradiance mesurée et la NOCT. |

*Berlin Demo utilise des capteurs simulés de puissance, d’irradiance et de température des modules.*

![Capteurs de puissance réelle, d’irradiance et de température des modules de Berlin Demo](docs/images/settings-sensors.png)

### Prévisions

Dans **Paramètres**, ouvrez **Prévisions** pour vérifier le lieu et le fuseau horaire. Modifiez-les dans Home Assistant. Le champ **Jours d’historique PR** fixe la période utilisée pour la correction. La valeur par défaut est de 14 jours.

### Surveillance

Par défaut, PVYieldLens calcule l’énergie et le PR pour chaque intervalle de 5 minutes. Les valeurs en direct sont moyennées sur les 60 dernières secondes et actualisées toutes les 5 secondes. Quand un capteur dépasse son **Délai sans données**, la période concernée compte comme manquante.

Sélectionnez **Enregistrer la configuration**.

## Résultats

### Tableau de bord

Comparez les puissances réelle et estimée, le **PR** et la **Puissance optimisable**. Le graphique **Données en direct** affiche les dix dernières minutes de puissance.

*Puissance et PR en direct pour Berlin Demo.*

![Tableau de bord de Berlin Demo avec la courbe en direct, la puissance actuelle et le PR](docs/images/dashboard.png)

Consultez **Données de production** pour voir la puissance, l’irradiance et la température des modules sur les intervalles clôturés de la journée.

*Production du jour et relevés des capteurs de Berlin Demo pour les intervalles clôturés.*

![Courbes de puissance, d’irradiance et de température des modules de Berlin Demo pour les intervalles clôturés](docs/images/dashboard-generation.png)

L’**Historique de production** compare chaque jour l’énergie réelle et estimée. Choisissez **7 jours**, **30 jours** ou **Personnalisé** pour une période de 90 dates au maximum. Pour voir les sept derniers jours complets comme dans Berlin Demo, choisissez **Personnalisé**, terminez la période hier et commencez-la six jours plus tôt. Sélectionnez **Appliquer**.

*Plage personnalisée de sept jours dans Berlin Demo avant validation.*

![Plage personnalisée de Berlin Demo avec les dates de début et de fin et le bouton « Appliquer »](docs/images/dashboard-history-range.png)

*Production quotidienne de Berlin Demo sur sept jours complets.*

![Historique de production de Berlin Demo comparant les énergies réelle et estimée sur sept jours complets](docs/images/dashboard-history.png)

Le PR en direct est le rapport en pourcentage entre la puissance réelle et la puissance estimée. Il peut dépasser 100 %. La **Puissance optimisable** (puissance estimée moins puissance réelle) peut être négative. Une donnée manquante laisse un blanc. Un zéro mesuré reste à zéro. Si la puissance estimée est nulle, le PR affiche **—**.

### Efficacité

Choisissez **Aujourd’hui**, **24 heures**, **7 jours** ou **30 jours**. **Aujourd’hui** compare la production à celle d’hier jusqu’à la même heure locale. **7 jours** inclut aujourd’hui.

Consultez le PR de la période, sa variation en points de pourcentage et l’écart entre l’énergie estimée et réelle. Suivez les variations dans **Évolution du PR** et **Comparaison de production**. Pour les plages calendaires, alternez entre **Résumé quotidien** et l’affichage par intervalle de règlement. Le PR sur la période est le rapport entre l’énergie réelle et l’énergie estimée sur les mêmes intervalles valides et clôturés.

*Dans Berlin Demo, la variation du PR est calculée en comparant aujourd’hui et hier jusqu’à la même heure locale.*

![Vue Efficacité de Berlin Demo aujourd’hui avec l’évolution du PR et la comparaison des puissances réelle et estimée](docs/images/efficiency.png)

### Prévisions

Comparez la **Prévision originale** et la **Prévision corrigée** pour aujourd’hui et les six prochains jours. La prévision originale utilise la météo d’Open-Meteo et les paramètres de l’installation. La correction utilise le PR récent pondéré par l’énergie et nécessite au moins trois jours complets admissibles dont l’énergie estimée est positive. En attendant, les valeurs corrigées affichent **—**.

Les cartes du haut affichent **Reste aujourd’hui** et **Prévision de demain**. Dans **Énergie prévue par jour**, **Aujourd’hui** couvre la journée entière et le **Total sur 7 jours** inclut les sept jours. Sélectionnez **Actualiser les prévisions** pour demander une mise à jour météo.

*Prévisions d’énergie originales et corrigées de Berlin Demo, choix de la date et bouton **Exporter le CSV**.*

![Vue d’ensemble des prévisions de Berlin Demo avec sept dates, les énergies originales et corrigées et le bouton Exporter le CSV](docs/images/forecast.png)

Sélectionnez une date pour comparer les courbes de puissance. Ouvrez **Détails par 15 minutes** pour voir la puissance, l’énergie, l’irradiance et les températures par intervalle.

*Courbes de puissance et détails par 15 minutes pour la date sélectionnée dans Berlin Demo.*

![Courbes de puissance de Berlin Demo pour la date sélectionnée et tableau des détails par 15 minutes](docs/images/forecast-details.png)

Pour utiliser EMHASS avec un seul onduleur photovoltaïque, sélectionnez **Exporter le CSV**, puis la série originale ou corrigée. Alignez le début, l’intervalle et le nombre de pas sur votre optimisation. Placez `data_weather_forecast.csv` dans le `data_path` d’EMHASS et réglez `set_use_pv=true` et `weather_forecast_method=csv`. [Configuration d’EMHASS](pvyieldlens/DOCS.md#export-a-pv-power-forecast-to-emhass)

*Paramètres d’exportation pour une exécution EMHASS dans Berlin Demo.*

![Boîte de dialogue d’exportation EMHASS de Berlin Demo avec la série, l’heure de début, l’intervalle et le nombre de pas](docs/images/forecast-export.png)

### Capteurs de sortie Home Assistant

| Mesure | Nom de l’entité HA | Unité |
| --- | --- | --- |
| Puissance estimée après clôture | `settled_estimated_power` | W |
| Puissance réelle après clôture | `settled_actual_power` | W |
| PR après clôture | `settled_pr` | % |
| Énergie estimée aujourd’hui | `estimated_energy_today` | kWh |
| Énergie estimée cumulée | `estimated_energy_lifetime` | kWh |
| Puissance estimée en direct | `live_estimated_power` | W |
| Puissance réelle en direct | `live_actual_power` | W |
| PR en direct | `live_pr` | % |
| Puissance optimisable en direct | `live_optimizable_power` | W |
| Énergie prévue aujourd’hui | `forecast_energy_today` | kWh |
| Énergie prévue pour le reste de la journée | `forecast_energy_remaining_today` | kWh |
| Énergie prévue demain | `forecast_energy_tomorrow` | kWh |
| Énergie prévue sur sept jours | `forecast_energy_7d` | kWh |

Le tableau reprend les noms affichés dans Home Assistant. Dans les automatisations, utilisez l’identifiant complet, par exemple `sensor.pvyieldlens_settled_estimated_power`. Les quatre capteurs de prévision indiquent l’énergie de la **Prévision originale**. L’énergie estimée du jour repart de zéro à minuit dans le fuseau horaire du domicile. Le cumul commence à la première configuration.
