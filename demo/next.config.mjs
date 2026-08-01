/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: the demo is a thesis artifact. It must open from a file
  // server or GitHub Pages years from now with no Node process running, and
  // archive cleanly alongside the Zenodo DOI.
  output: "export",
  images: { unoptimized: true },
};
export default nextConfig;
