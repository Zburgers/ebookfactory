/** Rootless Podman argument builder for one private production job. */

import { relative, resolve } from "node:path";

export const JOB_IMAGE =
  "localhost/ebook-factory-job@sha256:ceaa82d7c3272607253bc7426039354aa2677d3078775582501b9a551bf63f87";

export function validateWorkspace(root, workspace) {
  const rootPath = resolve(root);
  const workspacePath = resolve(workspace);
  const relativePath = relative(rootPath, workspacePath);
  if (!relativePath || relativePath.startsWith("..") || relativePath.startsWith("/")) {
    throw new Error("workspace must be a private child of the artifact root");
  }
  if (workspace.includes("\0")) throw new Error("invalid workspace path");
  return workspacePath;
}

export function buildPodmanArgs({ image = JOB_IMAGE, name, installId, jobId, generation, workspace, command }) {
  if (!name || !installId || !jobId || !Number.isInteger(generation)) throw new Error("job identity is required");
  if (!Array.isArray(command) || command.length === 0) throw new Error("trusted command is required");
  return [
    "run",
    "--rm",
    "--name", name,
    "--label", `io.ebook-factory.install=${installId}`,
    "--label", `io.ebook-factory.job=${jobId}`,
    "--label", `io.ebook-factory.generation=${generation}`,
    "--read-only",
    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m",
    "--cap-drop=all",
    "--security-opt=no-new-privileges",
    "--network=none",
    "--memory=128m",
    "--cpus=1",
    "--pids-limit=64",
    "--userns=keep-id",
    "--user", "ebook",
    "--mount", `type=bind,src=${workspace},dst=/workspace,rw,nodev,nosuid`,
    image,
    ...command,
  ];
}
