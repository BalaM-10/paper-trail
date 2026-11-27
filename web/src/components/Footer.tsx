/**
 * `repoUrl` comes from VITE_REPO_URL at build time. With no web address
 * there is nothing to link to, so nothing is shown.
 */
export function Footer({ repoUrl }: { repoUrl: string }) {
  if (!/^https?:\/\//i.test(repoUrl)) return null;
  return (
    <footer className="page-footer">
      <a href={repoUrl} target="_blank" rel="noopener noreferrer">
        View on GitHub
      </a>
    </footer>
  );
}
