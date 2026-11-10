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

[![Ajouter le dépôt d’apps PVYieldLens](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fenecess%2Fha-pvyieldlens)

1. Cliquez sur le bouton ci-dessus et confirmez **Ajouter** dans Home Assistant.
2. Trouvez **PVYieldLens** dans la boutique d’apps, puis installez et démarrez l’app.
3. Ouvrez la page Web, puis **Paramètres** pour choisir les capteurs et renseigner les panneaux.

Si le bouton n’ouvre pas Home Assistant, allez dans **Paramètres > Applications > Installer une application > menu en haut à droite > Dépôts** et ajoutez :

```text
https://github.com/enecess/ha-pvyieldlens
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

Ouvrez [localhost:8099](http://localhost:8099). Connectez-vous avec `admin` et le mot de passe choisi. Dans **Paramètres**, saisissez l’adresse Home Assistant et un jeton d’accès de longue durée appartenant à un **administrateur** Home Assistant, puis cliquez sur **Charger les capteurs**. Les droits d’administration sont nécessaires pour publier les capteurs de sortie.

Par défaut, la page est accessible sur la machine Docker. Pour y accéder depuis un autre appareil, remplacez `127.0.0.1:8099:8099` par `8099:8099` dans `compose.yaml`.

## Réglages

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

Enregistrez, puis ouvrez **Vue d’ensemble**. Le premier résultat de l’historique apparaît à la fin de la période en cours. Sous **Délai sans données**, réglez le temps d’attente pour chaque capteur.

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
