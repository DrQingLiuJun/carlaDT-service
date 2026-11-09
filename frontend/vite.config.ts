import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath, URL} from 'node:url';
export default defineConfig({root:fileURLToPath(new URL('.',import.meta.url)),plugins:[react()],server:{port:5173,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8765',changeOrigin:true},'/ws':{target:'ws://127.0.0.1:8765',ws:true}}},build:{outDir:'dist',emptyOutDir:true}});
