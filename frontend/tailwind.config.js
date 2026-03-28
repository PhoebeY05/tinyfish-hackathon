export default {
    content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
    theme: {
        extend: {
            fontFamily: {
                serif: ["'Playfair Display'", 'serif'],
                mono: ["'JetBrains Mono'", 'monospace'],
            },
            colors: {
                ink: '#0d0d0d',
                paper: '#f5f0e8',
                accent: '#2d5a1b',
                accent2: '#c8a84b',
                muted: '#6b6560',
                border: '#d4cfc6',
                danger: '#8b2020',
                success: '#1a4a0d',
            },
        },
    },
    plugins: [require('@tailwindcss/forms')],
};
