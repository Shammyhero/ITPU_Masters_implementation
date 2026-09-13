/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: the console is served by `airs serve` from the wheel, and the
  // evidence pages must also open from a file server years from now with no Node
  // process running, archived alongside the Zenodo DOI.
  output: "export",
  // /evidence/ exports as evidence/index.html, which a static file server — and
  // Starlette's StaticFiles(html=True) behind `airs serve` — serves as a directory.
  trailingSlash: true,
  images: { unoptimized: true },
};
export default nextConfig;
