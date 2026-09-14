import { z } from "zod";
import { ApiClientError } from "./client";
const ProjectSchema = z.object({
  project_id: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
const ChatSchema = ProjectSchema.extend({
  chat_id: z.string(),
  draft_prompt: z.string(),
  workflow_id: z.string().nullable(),
  document_pack_id: z.string().nullable(),
});
export type Project = z.infer<typeof ProjectSchema>;
export type Chat = z.infer<typeof ChatSchema>;
export class WorkspaceApi {
  constructor(private baseUrl: string) {}
  private async request(
    path: string,
    method = "GET",
    body?: unknown,
  ): Promise<unknown> {
    let response: Response;
    try {
      response = await fetch(new URL(`/workspace${path}`, this.baseUrl), {
        method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(15000),
      });
    } catch {
      throw new ApiClientError(
        0,
        path,
        "Le service local ne répond pas. Vérifiez qu’il est démarré, puis réessayez.",
      );
    }
    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = typeof payload?.detail === "string" ? payload.detail : "";
      } catch {
        detail = "";
      }
      throw new ApiClientError(
        response.status,
        path,
        detail ||
          (method === "GET"
            ? "L’espace de travail n’a pas pu être chargé. Réessayez."
            : "L’espace de travail n’a pas pu être enregistré. Réessayez."),
      );
    }
    if (response.status === 204) return null;
    try {
      return await response.json();
    } catch {
      throw new ApiClientError(
        502,
        path,
        "Le service local a renvoyé une réponse illisible. Rechargez la page.",
      );
    }
  }
  private parse<T>(schema: z.ZodType<T>, value: unknown): T {
    const parsed = schema.safeParse(value);
    if (!parsed.success)
      throw new ApiClientError(
        502,
        "/workspace",
        "Les données de l’espace de travail sont incohérentes. Rechargez la page.",
      );
    return parsed.data;
  }
  async projects() {
    return this.parse(ProjectSchema.array(), await this.request("/projects"));
  }
  async linkedWorkflowIds() {
    return this.parse(
      z.array(z.string()),
      await this.request("/linked-workflow-ids"),
    );
  }
  async createProject(title: string) {
    return this.parse(
      ProjectSchema,
      await this.request("/projects", "POST", { title }),
    );
  }
  async deleteProject(id: string) {
    await this.request(`/projects/${encodeURIComponent(id)}`, "DELETE");
  }
  async chat(id: string) {
    return this.parse(
      ChatSchema,
      await this.request(`/chats/${encodeURIComponent(id)}`),
    );
  }
  async chats(id: string) {
    return this.parse(
      ChatSchema.array(),
      await this.request(`/projects/${encodeURIComponent(id)}/chats`),
    );
  }
  async createChat(
    id: string,
    title: string,
    workflow_id?: string,
    draft_prompt = "",
  ) {
    return this.parse(
      ChatSchema,
      await this.request(`/projects/${encodeURIComponent(id)}/chats`, "POST", {
        title,
        workflow_id,
        draft_prompt,
      }),
    );
  }
  async updateChat(
    id: string,
    patch: Partial<
      Pick<Chat, "draft_prompt" | "title" | "workflow_id" | "document_pack_id">
    >,
  ) {
    return this.parse(
      ChatSchema,
      await this.request(`/chats/${encodeURIComponent(id)}`, "PATCH", patch),
    );
  }
  async deleteChat(id: string) {
    await this.request(`/chats/${encodeURIComponent(id)}`, "DELETE");
  }
}
