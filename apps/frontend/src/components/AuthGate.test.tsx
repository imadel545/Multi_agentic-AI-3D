import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" }
  }));
}

describe("AuthGate", () => {
  it("creates the first local owner from a user-chosen password", async () => {
    const fetcher = vi.fn()
      .mockImplementationOnce(() => jsonResponse({
        enabled: true, setup_required: true, authenticated: false
      }))
      .mockImplementationOnce(() => jsonResponse({
        enabled: true, setup_required: false, authenticated: true
      }));
    vi.stubGlobal("fetch", fetcher);
    render(<AuthGate><p>Studio privé</p></AuthGate>);

    expect(await screen.findByRole("heading", { name: "Créer mon compte" })).toBeInTheDocument();
    expect(screen.queryByText("Studio privé")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Votre nom"), { target: { value: "Alice Martin" } });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "alice@circet.example" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), {
      target: { value: "correct horse battery staple" }
    });
    fireEvent.change(screen.getByLabelText("Confirmer le mot de passe"), {
      target: { value: "correct horse battery staple" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));

    expect(await screen.findByText("Studio privé")).toBeInTheDocument();
    const setupCall = fetcher.mock.calls[1];
    expect(String(setupCall[0])).toMatch(/\/auth\/register$/);
    expect(setupCall[1]).toMatchObject({ method: "POST", credentials: "include" });
    expect(JSON.parse(String(setupCall[1].body))).toEqual({
      password: "correct horse battery staple", email: "alice@circet.example", display_name: "Alice Martin"
    });
  });

  it("returns to login when the API reports an expired session", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({
      enabled: true, setup_required: false, authenticated: true
    })));
    render(<AuthGate><p>Studio privé</p></AuthGate>);
    expect(await screen.findByText("Studio privé")).toBeInTheDocument();

    window.dispatchEvent(new Event("telecom-auth-required"));

    expect(await screen.findByRole("heading", { name: "Se connecter" })).toBeInTheDocument();
    expect(screen.queryByText("Studio privé")).not.toBeInTheDocument();
  });

  it("keeps the gate closed after an invalid password", async () => {
    const fetcher = vi.fn()
      .mockImplementationOnce(() => jsonResponse({
        enabled: true, setup_required: false, authenticated: false
      }))
      .mockImplementationOnce(() => jsonResponse({ detail: "Invalid password." }, 401));
    vi.stubGlobal("fetch", fetcher);
    render(<AuthGate><p>Studio privé</p></AuthGate>);
    await screen.findByRole("heading", { name: "Se connecter" });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "alice@circet.example" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), {
      target: { value: "incorrect password" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Adresse e-mail ou mot de passe incorrect");
    expect(screen.queryByText("Studio privé")).not.toBeInTheDocument();
  });

  it("bypasses the page only when the server explicitly disables auth", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({
      enabled: false, setup_required: false, authenticated: true
    })));
    render(<AuthGate><p>Studio privé</p></AuthGate>);

    await waitFor(() => expect(screen.getByText("Studio privé")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Se déconnecter" })).not.toBeInTheDocument();
  });

  it("does not claim logout when server revocation fails", async () => {
    const fetcher = vi.fn()
      .mockImplementationOnce(() => jsonResponse({
        enabled: true, setup_required: false, authenticated: true
      }))
      .mockRejectedValueOnce(new Error("network unavailable"));
    vi.stubGlobal("fetch", fetcher);
    render(<AuthGate><p>Studio privé</p></AuthGate>);
    await screen.findByText("Studio privé");

    fireEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("déconnexion n’a pas pu être confirmée");
    expect(screen.getByText("Studio privé")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Se connecter" })).not.toBeInTheDocument();
  });
});


it("validates signup fields before contacting the API and focuses the first invalid field", async () => {
  const fetcher = vi.fn(() => jsonResponse({ enabled: true, setup_required: true, authenticated: false }));
  vi.stubGlobal("fetch", fetcher);
  render(<AuthGate><p>Studio privé</p></AuthGate>);
  await screen.findByRole("heading", { name: "Créer mon compte" });
  fireEvent.click(screen.getByRole("button", { name: "Créer mon compte" }));
  expect(screen.getByLabelText("Votre nom")).toHaveFocus();
  expect(screen.getByLabelText("Votre nom")).toHaveAttribute("aria-invalid", "true");
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Mot de passe")).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Afficher le mot de passe" }));
  expect(screen.getByLabelText("Mot de passe")).toHaveAttribute("type", "text");
});

it("keeps email login after a successful logout from a named account", async () => {
  const fetcher = vi.fn().mockImplementationOnce(() => jsonResponse({
    enabled: true, setup_required: false, authenticated: true, requires_email: true, requires_username: false,
    profile: { display_name: "Alice Martin", email: "alice@circet.example" }
  })).mockImplementationOnce(() => jsonResponse({ authenticated: false }));
  vi.stubGlobal("fetch", fetcher);
  render(<AuthGate><p>Studio privé</p></AuthGate>);
  expect(await screen.findByText("Alice Martin")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));
  expect(await screen.findByRole("heading", { name: "Se connecter" })).toBeInTheDocument();
  expect(screen.getByLabelText("Adresse e-mail")).toBeInTheDocument();
  expect(screen.queryByText("Studio privé")).not.toBeInTheDocument();
});


it("shows an email/password login page and a real signup link on an empty studio", async () => {
  window.history.replaceState(null, "", "/login");
  const fetcher = vi.fn().mockImplementationOnce(() => jsonResponse({
    enabled: true, setup_required: true, authenticated: false, requires_email: false
  })).mockImplementationOnce(() => jsonResponse({
    enabled: true, setup_required: false, authenticated: true, requires_email: true
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<AuthGate><p>Studio privé</p></AuthGate>);
  expect(await screen.findByRole("heading", { name: "Se connecter" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Votre nom")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Confirmer le mot de passe")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Créer mon compte" })).toHaveAttribute("href", "/register");
  fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "alice@circet.example" } });
  fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "correct horse battery staple" } });
  fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
  await screen.findByText("Studio privé");
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({email:"alice@circet.example",password:"correct horse battery staple"});
  expect(window.location.pathname).toBe("/");
});

it("rejects a malformed email before registration and removes the unwanted brand note", async () => {
  const fetcher = vi.fn(() => jsonResponse({ enabled:true, setup_required:true, authenticated:false }));
  vi.stubGlobal("fetch", fetcher);
  render(<AuthGate><p>Studio privé</p></AuthGate>);
  await screen.findByRole("heading", { name:"Créer mon compte" });
  expect(screen.getByRole("link", { name:"Se connecter" })).toHaveAttribute("href","/login");
  expect(screen.queryByText("Un accès personnel à votre studio.")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Votre nom"), {target:{value:"Alice Martin"}});
  fireEvent.change(screen.getByLabelText("Adresse e-mail"), {target:{value:"bad-email"}});
  fireEvent.click(screen.getByRole("button",{name:"Créer mon compte"}));
  expect(screen.getByLabelText("Adresse e-mail")).toHaveFocus();
  expect(screen.getByText("Indiquez une adresse e-mail valide.")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("preserves login for a historical username owner without fabricating an email", async () => {
  vi.stubGlobal("fetch",vi.fn(() => jsonResponse({enabled:true,setup_required:false,authenticated:false,requires_email:false,requires_username:true})));
  render(<AuthGate><p>Studio privé</p></AuthGate>);
  await screen.findByRole("heading",{name:"Se connecter"});
  expect(screen.getByLabelText("Identifiant existant")).toBeInTheDocument();
  expect(screen.queryByLabelText("Adresse e-mail")).not.toBeInTheDocument();
  expect(screen.queryByRole("link",{name:"Créer mon compte"})).not.toBeInTheDocument();
});
