// Babylon loads its configured Meshopt decoder URL as a classic script.
// asset-codecs.ts installs the package's ESM decoder on globalThis beforehand.
globalThis.MeshoptDecoder = globalThis.MeshoptDecoder;
