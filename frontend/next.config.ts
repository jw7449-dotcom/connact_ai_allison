import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  devIndicators: false,
  // OAuth callbacks carry short-lived authorization codes in their query.
  logging: {
    incomingRequests: {
      ignore: [
        /\/api\/auth\//,
        /\/api\/mailboxes\/callback/,
        /\/api\/mail\/unsubscribe\//,
      ],
    },
  },
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default config;
