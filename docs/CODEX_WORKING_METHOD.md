# Codex Working Method

Méthode obligatoire pour tout agent Codex travaillant sur ce projet.

---

## 1. Audit

Avant toute modification :

- Lire `AGENTS.md`.
- Lire `docs/PROJECT_SOURCE_OF_TRUTH.md`.
- Lire `docs/BACKEND_CAPABILITY_MATRIX.md`.
- Identifier les fichiers concernés.
- Comprendre le flux de données réel (endpoint → service → contract → output).

## 2. Diagnostic

- Expliquer le problème en une phrase.
- Citer le fichier et la ligne si possible.
- Ne pas supposer que "ça devrait marcher".
- Vérifier avec les tests ou une exécution réelle.

## 3. Plan minimal

- Proposer la plus petite modification qui résout le problème.
- Ne pas ajouter de scope caché.
- Si plusieurs approches, les présenter avec trade-offs.

## 4. Implémentation safe

- Modifier uniquement les fichiers nécessaires.
- Ne pas faire `git add -A`.
- Ne pas ajouter de mocks/fake permanents.
- Respecter le style existant.

## 5. Tests

- Ajouter ou mettre à jour des tests unitaires si le projet en a.
- Exécuter `pytest` pour le backend.
- Exécuter `npm run test` pour le frontend.

## 6. Smoke runtime

- Vérifier que le backend démarre.
- Vérifier qu'un endpoint clé répond correctement.
- Vérifier qu'aucune exception silencieuse n'est ajoutée.

## 7. Smoke visuel (si UI)

- Vérifier `npm run typecheck`.
- Vérifier `npm run build`.
- Si possible, capture d'écran du résultat visuel.
- Aucune erreur console.

## 8. Sync documentation vérité

- Mettre à jour `AGENTS.md`, `PROJECT_SOURCE_OF_TRUTH.md`, ou `BACKEND_CAPABILITY_MATRIX.md` si une capability change de statut.
- Ne pas créer de documentation marketing.

## 9. Git status

- `git status --short`.
- `git diff --check`.
- Classifier chaque changement.

## 10. Commit sélectif

- `git add <fichiers nécessaires uniquement>`.
- Message de commit clair et honnête.
- Ne jamais commiter `node_modules/`, `dist/`, `outputs/`, `data/`, `.env`, caches.

## 11. Rapport honnête

- Résumer ce qui a été fait.
- Lister ce qui fonctionne et ce qui reste limité.
- Ne pas dire "ready" sans preuve.
- Indiquer la prochaine étape recommandée.

---

## Interdictions

- Patcher sans audit.
- Déclarer ready sans preuve.
- Masquer les limites.
- Valider seulement avec build OK.
- Créer UI fake.
- Exposer logs techniques comme UI.
- Ignorer screenshots utilisateur.
- Continuer sur une mauvaise base.
