import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            '/uploads': 'http://localhost:3000',
            '/jobs': 'http://localhost:3000',
        },
    },
});
