# AGENTS.md — Agentic AI 3D Telecom Design Studio

Ce fichier est la règle d'or pour tout agent Codex travaillant sur ce repo.  
Il est court, strict et non négociable.

---

## 1. Avant d'écrire du code

- Lire `docs/PROJECT_SOURCE_OF_TRUTH.md`.
- Lire `docs/BACKEND_CAPABILITY_MATRIX.md`.
- Lire `docs/KNOWN_LIMITATIONS.md`.
- Auditor le endpoint/backend concerné avant de modifier quoi que ce soit.
- Ne jamais présumer qu'une capability est opérationnelle sans preuve (test, log, ou réponse API).

## 2. Ce qui est interdit

- **Pas de fake** : pas de données mockées, pas de GLB placeholder présenté comme un vrai design, pas de statut `completed` sans vérification réelle.
- **Pas de dashboard dev** : le frontend actuel est refusé. Ne pas reconstruire de layout dashboard. La prochaine UI sera chat-first et 3D-first.
- **Pas de logs/codes techniques comme UI principale** : l'utilisateur final ne doit pas lire `workflow_trace.json` ou des codes d'erreur bruts.
- **Pas de "ready" sans preuve** : tout "terminé" doit être accompagné de tests, de smoke runtime et, si UI, de preuve visuelle.
- **Pas de `git add -A`** : chaque fichier commité est choisi explicitement.
- **Pas de commit de artefacts** : jamais `node_modules/`, `dist/`, `outputs/`, `data/qdrant/`, `data/sqlite/`, `.env`, caches, screenshots temporaires.
- **Pas de documentation marketing** : les docs disent la vérité, avec limitations et statuts précis.

## 3. Sources de vérité

- **Backend** : les endpoints FastAPI et les fichiers JSON qu'ils produisent.
- **3D** : `SceneSpec` est la source de vérité de génération.
- **Document pack** : `ProjectDesignSpec` est la source de vérité documentaire.
- **Assets** : les manifests JSON sous `assets/manifests` et l'existence réelle des fichiers GLB.
- **LLM** : Groq `openai/gpt-oss-120b` par défaut ; extraction déterministe comme fallback explicite.

## 4. Documents actifs vs archive

Les documents actifs du projet sont :

- `AGENTS.md`
- `docs/PROJECT_SOURCE_OF_TRUTH.md`
- `docs/BACKEND_CAPABILITY_MATRIX.md`
- `docs/FRONTEND_PRODUCT_BLUEPRINT.md`
- `docs/FRONTEND_ACCEPTANCE_CRITERIA.md`
- `docs/CODEX_WORKING_METHOD.md`
- `docs/API_FRONTEND_CONTRACT.md`
- `docs/KNOWN_LIMITATIONS.md`

`docs/archive/` est historique uniquement et ne doit pas être utilisé comme source de vérité active sauf demande explicite.

## 5. Fallbacks et warnings

- Tout fallback doit être **visible** dans l'API, les rapports, et l'UI finale.
- Les warnings doivent être exprimés en **langage utilisateur**, pas en codes techniques.
- Si Blender manque, le workflow doit échouer proprement ou être explicitement marqué comme fallback non valide.
- Si une extraction LLM échoue, le fallback déterministe est utilisé et signalé.

## 6. Frontend

- Le frontend actuel sous `apps/frontend` est **refusé**.
- Le prochain frontend sera :
  - **chat-first** : la zone de commande principale est une conversation.
  - **3D-first** : le viewer 3D occupe la majorité de l'écran.
  - **drawers contextuels** : QA, documents, versions, assets ouverts en drawers, jamais en panneaux fixes vides.
  - **simple** : l'utilisateur comprend quoi faire en moins de 5 secondes.
- Ne pas reconstruire le frontend dans cette mission sans autorisation explicite.

## 7. Méthode de travail

1. Audit.
2. Diagnostic.
3. Plan minimal.
4. Implémentation safe et ciblée.
5. Tests.
6. Smoke runtime.
7. Smoke visuel si UI.
8. Synchronisation de la documentation vérité.
9. `git status` propre.
10. Commit sélectif.
11. Rapport honnête.

## 8. Scope

- Local-first, mono-utilisateur.
- Pas de SaaS multi-user, pas de PostgreSQL, pas de Kubernetes, pas de microservices.
- Pas de génération libre de code Blender par LLM.
- Pas de fusion avec image réelle, pas de RA mobile, pas de Google Maps.

## 9. Rappel final

> Ce projet produit des modèles 3D techniques vérifiables, pas des démos visuelles.  
> La qualité est mesurée par la vérité du backend, pas par l'optimisme des docs.
