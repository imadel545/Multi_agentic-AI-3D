# Frontend Acceptance Criteria

Ces critères acceptent le frontend produit, pas seulement ses composants. Les
preuves d'exécution datées sont centralisées dans
[PROJECT_SOURCE_OF_TRUTH.md](PROJECT_SOURCE_OF_TRUTH.md). Une case ouverte reste
un travail à démontrer sur le runtime réel.

## 1. Compréhension immédiate

- [ ] Confirmer par un essai utilisateur que la première action est comprise
  en moins de 5 secondes.
- [x] Le chat, la pièce jointe et le champ de commande sont visibles sans scroll
  sur le layout desktop nominal.

## 2. Viewer 3D dominant

- [x] Le viewer occupe la majorité de l'espace utile.
- [x] Un modèle vérifié est visible, grand et cadré au chargement.
- [x] Une tour haute reste lisible sans être coupée ni noyée dans le sol.

## 3. Chat comme commande

- [x] Le chat est la zone de commande principale.
- [ ] L'utilisateur peut générer, éditer, joindre un document et voir tout l'état
  utile depuis le chat dans un même parcours navigateur enregistré.
- [x] Les réponses et erreurs sont en langage utilisateur, sans codes internes.

## 4. Pièces jointes

- [x] Le composeur accepte plusieurs fichiers directs ou un ZIP, affiche les noms
  sélectionnés, permet le retrait individuel et respecte les limites backend.
- [x] Une pièce jointe restaurée reste compacte; extraction, scores, identifiants
  et diagnostics internes ne deviennent pas l'interface principale.
- [x] Le bouton `×` appelle la suppression gardée et distingue explicitement le
  succès de l'échec.
- [x] Un document enrichit seulement une commande non vide; il ne déclenche pas
  une génération autonome.

## 5. Surfaces contextuelles

- [x] Aucun grand panneau vide ou placeholder permanent.
- [x] Les drawers Composition, Livrables et Versions s’ouvrent à la demande
  avec un contenu utile.
- [x] La timeline détaillée reste contextuelle; seule l'opération active est
  visible dans la conversation.
- [x] Rapports, warnings et fallbacks sont résumés en langage utilisateur. Aucun
  JSON brut n'est rendu comme surface produit.

## 6. État et temps réel

- [x] La progression vient des phases et événements SSE, avec polling de reprise
  prévu par le contrat.
- [x] Génération, succès, échec et dégradation sont distincts; l'UI ne fabrique
  ni transcript de raisonnement ni streaming de tokens.
- [x] Les fallbacks Blender, asset et LLM restent visibles.
- [x] Une sortie `GeometryProgram` réparée est distinguée d'une sortie structurée
  acceptée directement.

## 7. Fonctions produit

- [x] Générer depuis une commande.
- [x] Joindre un document pack et le combiner à une commande non vide.
- [x] Modifier un design par commande.
- [x] Restaurer une version.
- [ ] Télécharger les artifacts depuis les contrôles du navigateur.
- [ ] Comprendre et confirmer un composant hors catalogue avant génération.
- [x] Afficher la provenance, l'enveloppe et les ajustements d'un composant
  `GeometryProgram`.
- [ ] Modifier un composant généré et constater la nouvelle version dans un smoke
  navigateur enregistré.
- [ ] Expliquer l'échec du spécialiste géométrique avant Blender.

## 8. Qualité technique

- [x] La suite frontend courante passe sans dépendre d'un nombre historique figé.
- [x] TypeScript et le build de production passent.
- [x] Le frontend valide les réponses backend aux frontières avec Zod.
- [x] Une session navigateur enregistrée charge le studio et un GLB réel sans
  erreur applicative console ou réponse réseau inattendue.
- [x] Le drawer Bibliothèque montre qu'un candidat constructeur exclu de la
  génération reste une preuve incomplète et ne propose pas de l'utiliser.
- [x] Le layout desktop et portrait garde le viewer et le chat utilisables.

## 9. Preuve visuelle

- [x] Un design `real_blender` est visible dans le viewer.
- [x] Le cadrage montre le modèle à une échelle utile.
- [x] Un clic sur un composant exporté cadre son sous-assemblage prouvé et garde
  l'identité utilisateur lisible.
- [x] Une conversation restaurée montre création, édition ciblée, refus et
  rollback sans exposer les racines sémantiques backend.
- [ ] Parcours navigateur enregistré pour création puis révision d'un
  `GeometryProgram`; une preuve backend seule ne ferme pas cette case.

## Rejet automatique

Le frontend est rejeté si le viewer n'est pas dominant, si l'interface redevient
un dashboard technique, si elle expose les codes/JSON internes comme contenu
principal, si elle affiche un panneau vide permanent, si les tests/build échouent,
ou si elle présente une preview ou un fallback comme un modèle 3D vérifié.

## Authentification et durée de tâche

- [x] La page Circet permet l’inscription du propriétaire local avec nom,
  identifiant et mot de passe; erreurs de champs, focus et affichage du mot de
  passe vérifiés sur desktop et écran étroit.
- [x] Les routes produit refusent une session absente; la déconnexion révoque
  la session serveur. Aucun identifiant par défaut n’est livré.
- [x] Le temps écoulé repose sur le début réel de l’opération, continue pendant
  son exécution puis se fige à la fin; le rechargement conserve les bornes serveur.
