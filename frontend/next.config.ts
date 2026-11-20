import type { NextConfig } from 'next';

const config: NextConfig = {
  output: process.env.NEXUS_ATENDE_STANDALONE === '1' ? 'standalone' : undefined,
  async rewrites() {
    const api = process.env.NEXUS_ATENDE_API_URL ?? 'http://127.0.0.1:8085';
    return [{ source: '/api/v1/:path*', destination: `${api}/api/v1/:path*` }];
  },
};

export default config;
