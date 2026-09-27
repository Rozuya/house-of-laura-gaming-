# House of Laura

Fan game promotionnel réalisé pour la streameuse **House of Laura**.
**Créé par Rozuya** 🌸

| Quoi | Où | Sur GitHub ? |
|---|---|---|
| Le site (4 pages) | `index.html`, `episode-1.html`, `episode-2.html`, `telechargement.html` | ✅ oui |
| Les jeux | `builds/episode-01/` | ❌ jamais (100 Mo) |
| Le code du jeu | `source/episode-01/` | ✅ oui, ~700 Ko |
| Les archives ZIP | `archive/` | ❌ non, régénérées |

---

## Le site : 4 pages, un seul bouton de téléchargement

```text
index.html           Accueil : présentation + liens vers les épisodes
episode-1.html       Le Signal Perdu : résumé, contenu, avertissements
episode-2.html       En préparation (aucun téléchargement ici)
telechargement.html  ⬇️ LE SEUL bouton de téléchargement du site
assets/css/style.css CSS commun à toutes les pages
assets/js/main.js    Menu mobile + année du pied de page
assets/images/       houseoflaura.png
```

**Règle du site :** le bouton de téléchargement existe **uniquement** dans
`telechargement.html`. Les autres pages y mènent par un lien, jamais par un
deuxième bouton. La page `episode-2.html` n'a **aucun** téléchargement, puisque
l'épisode 2 n'existe pas encore.

---

## Mettre le site en ligne (2 minutes)

**1. Crée le dépôt** sur github.com, nommé :

```text
house-of-laura
```

> GitHub n'accepte que `a-z`, `0-9`, `-`, `_`, `.` : pas d'accents, pas d'espace.
> URL finale : `https://TON-PSEUDO.github.io/house-of-laura/`

**2. Pousse les fichiers** (en ligne de commande, pour que `.gitignore` fasse son travail) :

```powershell
cd "C:\chemin\vers\house-of-laura"
git init
git branch -M main
git add .
git commit -m "House of Laura v1.2.0 - site multi-pages et episode 1"
git remote add origin https://github.com/TON-PSEUDO/house-of-laura.git
git push -u origin main
```

> ⚠️ **N'utilise pas le glisser-déposer de l'interface web de GitHub** : il
> ignorerait `.gitignore` et tenterait d'envoyer le `.exe` de 100 Mo, qui sera
> refusé. La ligne de commande est obligatoire ici.

**3. Active GitHub Pages** : `Settings` → `Pages` → *Build and deployment* :

- **Source** : `Deploy from a branch`
- **Branch** : `main`
- **Folder** : `/` (racine) ← `index.html` est déjà à la racine

Attends 1 à 2 minutes. ✅

---

## La seule chose à faire une fois : le lien de téléchargement

Dans `telechargement.html`, remplace le `href` marqué `↓↓↓` :

```html
href="DOWNLOAD_EP1"
```

par ton vrai lien (page itch.io ou lien direct vers le `.exe`).

Puis **reporte la même URL** dans `project.json` :

```json
"downloads": {
  "episode-01": "ton-lien-identique"
}
```

`build.py` vérifie que les deux correspondent et refuse de construire une
archive avec un bouton cassé.

---

## Générer l'archive ZIP

```powershell
py build.py                # archive/HouseOfLaura-v1.2.0.zip + MANIFEST.txt
py build.py --check        # vérifie sans rien créer
py build.py --no-source    # sans le code du jeu
```

`build.py` vérifie : chaque page existe, chaque lien entre pages pointe vers une
page réelle, chaque build est présent et complet, chaque URL de téléchargement
apparaît bien dans le site.

> ⚠️ Le ZIP fait ~96 Mo à cause du `.exe`. C'est normal : un ZIP compresse mal un
> exécutable déjà compressé.

---

## Ajouter une page ou l'Épisode 2

Toute page nouvelle doit être déclarée dans **deux endroits** de `project.json`,
sinon `build.py` ne l'embarque pas et ne la vérifie pas :

```json
"site": {
  "include":   [ "...", "episode-3.html" ],
  "required":  [ "...", "episode-3.html" ]
}
```

La procédure complète pour l'Épisode 2 est dans
**[`docs/AJOUTER-EPISODE-2.md`](docs/AJOUTER-EPISODE-2.md)**.

---

## Règles à ne pas casser

1. **`index.html` reste à la racine.** Si tu le déplaces, change le champ
   *Folder* dans `Settings → Pages`.
2. **Un dossier par épisode** : `builds/episode-01/`, `builds/episode-02/`…
3. **La version est dans le nom du fichier** : `HouseOfLaura-EP1-v1.2.0.exe`.
   Jamais `-FINAL`.
4. **Un seul bouton de téléchargement**, dans `telechargement.html`.
5. **Jamais de `.exe` sur GitHub** : limite 100 Mo/fichier, quota gratuit 2 Go.
   Distribution via itch.io.
6. **Chemins en minuscules.** GitHub Pages distingue la casse :
   `assets/images/houseoflaura.png`, pas `Assets/Images/HouseOfLaura.png`.
7. **`<nav aria-label="Navigation principale">`** doit rester unique par page :
   le CSS `.nav-link.active` s'appuie sur cette structure.
