/** `repoUrl` comes from VITE_REPO_URL at build time; "#" when it is not set. */
export function Footer({ repoUrl }: { repoUrl: string }) {
  const external = repoUrl !== "#";
  return (
    <footer className="page-footer">
      <a
        href={repoUrl}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      >
        View on GitHub
      </a>
    </footer>
  );
}
