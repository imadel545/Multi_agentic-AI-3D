import { ArrowRight, Eye, EyeOff, LoaderCircle, LogOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../api/client";

type AuthStatus = {
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  requires_username?: boolean;
  requires_email?: boolean;
  expires_at?: number | null;
  profile?: { display_name: string; email?: string; username?: string };
};
type FieldName = "display_name" | "email" | "username" | "password" | "confirmation";
type FieldErrors = Partial<Record<FieldName, string>>;

async function authRequest(path: string, body?: Record<string, string>, method?: string): Promise<AuthStatus> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(new URL(path, api.baseUrl), {
      method: method ?? (body ? "POST" : "GET"),
      credentials: "include",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("Adresse e-mail ou mot de passe incorrect.");
      if (response.status === 429) throw new Error("Trop de tentatives. Réessayez dans quelques minutes.");
      if (response.status === 409) throw new Error(path === "/auth/login"
        ? "Aucun compte n’est encore créé dans ce studio. Utilisez le lien de création de compte."
        : "Un compte existe déjà pour ce studio. Actualisez pour vous connecter.");
      if (response.status === 403) throw new Error("Ouvrez le studio depuis ce poste pour créer votre compte.");
      if (response.status === 422) throw new Error("Vérifiez les informations saisies avant de réessayer.");
      throw new Error("Le studio ne peut pas confirmer cette opération. Réessayez dans un instant.");
    }
    return await response.json() as AuthStatus;
  } catch (reason) {
    if (controller.signal.aborted) throw new Error("Le studio met trop de temps à répondre. Actualisez pour vérifier votre connexion avant de réessayer.");
    throw reason;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [values, setValues] = useState<Record<FieldName, string>>({ display_name: "", email: "", username: "", password: "", confirmation: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const pending = useRef(false);
  const inputs = useRef<Partial<Record<FieldName, HTMLInputElement | null>>>({});
  const clearSecrets = () => {
    setValues((current) => ({ ...current, password: "", confirmation: "" }));
    setShowPassword(false);
  };
  const refresh = useCallback(async () => {
    setError(null);
    try {
      setStatus(await authRequest("/auth/status"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Connexion au studio indisponible.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const requireAuthentication = () => {
      setStatus((current) => ({
        enabled: true, setup_required: current?.setup_required ?? false,
        requires_username: current?.requires_username, requires_email: current?.requires_email, authenticated: false
      }));
      clearSecrets();
      setErrors({});
      setError("Votre session a expiré. Connectez-vous pour continuer.");
    };
    window.addEventListener("telecom-auth-required", requireAuthentication);
    return () => window.removeEventListener("telecom-auth-required", requireAuthentication);
  }, [refresh]);

  const setup = status?.setup_required === true && window.location.pathname !== "/login";
  // Existing password/username owners remain reachable without inventing an email.
  const legacyLogin = status?.setup_required === false && status.requires_email === false;
  const withUsername = legacyLogin && status?.requires_username === true;
  const withEmail = !legacyLogin;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending.current) return;
    const nextErrors: FieldErrors = {};
    if (setup && (values.display_name.trim().length < 2 || values.display_name.trim().length > 80)) nextErrors.display_name = "Indiquez un nom de 2 à 80 caractères.";
    if (withEmail && (!values.email.trim() || inputs.current.email?.validity.typeMismatch)) nextErrors.email = "Indiquez une adresse e-mail valide.";
    if (withUsername && !values.username.trim()) nextErrors.username = "Indiquez l’identifiant de votre compte existant.";
    if (values.password.length < 12 || values.password.length > 256) nextErrors.password = "Utilisez entre 12 et 256 caractères.";
    if (setup && values.password !== values.confirmation) nextErrors.confirmation = "Les deux mots de passe ne correspondent pas.";
    setErrors(nextErrors);
    setError(null);
    const firstError = Object.keys(nextErrors)[0] as FieldName | undefined;
    if (firstError) { inputs.current[firstError]?.focus(); return; }
    pending.current = true;
    setBusy(true);
    try {
      const body = { password: values.password, ...(withEmail ? { email: values.email.trim() } : {}), ...(withUsername ? { username: values.username.trim() } : {}), ...(setup ? { display_name: values.display_name.trim() } : {}) };
      setStatus(await authRequest(setup ? "/auth/register" : "/auth/login", body));
      if (["/login", "/register"].includes(window.location.pathname)) window.history.replaceState(null, "", `/${window.location.search}${window.location.hash}`);
      clearSecrets();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Connexion au studio impossible.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  const logout = async () => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await authRequest("/auth/logout", undefined, "POST");
      setStatus({ enabled: true, authenticated: false, setup_required: false, requires_username: status?.requires_username, requires_email: status?.requires_email });
      clearSecrets();
    } catch {
      setError("La déconnexion n’a pas pu être confirmée par le studio. Réessayez.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  if (status?.authenticated || status?.enabled === false) {
    return <>
      {children}
      {status.enabled && error ? <p className="auth-logout-error" role="alert">{error}</p> : null}
      {status.enabled ? <div className="auth-session">
        {status.profile ? <span title={status.profile.display_name}>{status.profile.display_name}</span> : null}
        <button disabled={busy} onClick={() => void logout()} type="button"><LogOut size={15} aria-hidden="true" /> Se déconnecter</button>
      </div> : null}
    </>;
  }

  const field = (name: FieldName, label: string, help?: string) => {
    const secret = name === "password" || name === "confirmation";
    const id = `auth-${name}`;
    return <div className="auth-field" key={name}>
      <label htmlFor={id}>{label}</label>
      <div className={secret ? "auth-password" : undefined}>
        <input id={id} name={name} ref={(node) => { inputs.current[name] = node; }}
          type={secret && !showPassword ? "password" : name === "email" ? "email" : "text"}
          autoComplete={name === "display_name" ? "name" : (name === "username" || name === "email") ? "username" : setup ? "new-password" : "current-password"}
          autoCapitalize={name === "username" || name === "email" ? "none" : undefined} spellCheck={false}
          required disabled={busy} value={values[name]} maxLength={secret ? 256 : name === "email" ? 254 : name === "username" ? 64 : 80}
          aria-invalid={Boolean(errors[name])}
          aria-describedby={[help ? `${id}-help` : "", errors[name] ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined}
          onChange={(event) => {
            const value = event.currentTarget.value;
            setValues((current) => ({ ...current, [name]: value }));
            setErrors((current) => ({ ...current, [name]: undefined }));
          }} />
        {secret ? <button type="button" className="auth-reveal" disabled={busy} aria-label={`${showPassword ? "Masquer" : "Afficher"} ${name === "confirmation" ? "la confirmation du mot de passe" : "le mot de passe"}`} aria-pressed={showPassword} onClick={() => setShowPassword((current) => !current)}>
          {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button> : null}
      </div>
      {help ? <small id={`${id}-help`}>{help}</small> : null}
      {errors[name] ? <p id={`${id}-error`} className="auth-field-error">{errors[name]}</p> : null}
    </div>;
  };

  return <main className="auth-gate">
    <div className="auth-layout">
      <aside className="auth-brand" aria-label="Circet Studio">
        <img className="auth-logo" src="/brand/circet-logo.jpg" alt="Circet — Créateur de réseaux" width="1280" height="688" />
        <h2>Vos projets télécom, <span>en trois dimensions.</span></h2>
        <p>Décrivez votre site, joignez vos plans et affinez votre modèle depuis la conversation.</p>
      </aside>
      <section className="auth-card" aria-labelledby="auth-title">
        <h1 id="auth-title">{setup ? "Créer mon compte" : "Se connecter"}</h1>
        <p className="auth-intro">{setup ? "Configurez votre accès pour commencer un premier projet." : "Retrouvez vos projets et poursuivez votre conception."}</p>
        {status ? <form onSubmit={(event) => void submit(event)} noValidate aria-busy={busy}>
          {setup ? field("display_name", "Votre nom") : null}
          {withEmail ? field("email", "Adresse e-mail") : null}
          {withUsername ? field("username", "Identifiant existant") : null}
          {field("password", "Mot de passe", setup ? "12 caractères minimum. Une phrase de passe est acceptée." : undefined)}
          {setup ? field("confirmation", "Confirmer le mot de passe") : null}
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="auth-submit" disabled={busy} type="submit">
            {busy ? <LoaderCircle className="auth-spinner" size={18} aria-hidden="true" /> : null}
            {busy ? (setup ? "Création du compte…" : "Connexion…") : (setup ? "Créer mon compte" : "Se connecter")}
            {!busy ? <ArrowRight size={17} aria-hidden="true" /> : null}
          </button>
        </form> : error ? <p className="auth-error" role="alert">{error}</p> : <p className="auth-loading" role="status"><LoaderCircle className="auth-spinner" size={18} aria-hidden="true" /> Connexion au studio…</p>}
        {error ? <button type="button" className="auth-refresh" disabled={busy} onClick={() => void refresh()}>Actualiser la connexion</button> : null}
        {status?.setup_required ? <p className="auth-switch">{setup ? <>Déjà un compte ? <a href="/login">Se connecter</a></> : <>Première visite ? <a href="/register">Créer mon compte</a></>}</p> : null}
        <p className="auth-footer">{setup ? "Un compte pour ce studio local. Aucun e-mail de confirmation n’est nécessaire." : "Votre compte et vos projets restent dans ce studio local."}</p>
      </section>
    </div>
  </main>;
}
