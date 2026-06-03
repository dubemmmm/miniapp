/** Tailwind config — compiled by the standalone CLI (no Node deps).
 *  Build:  ./bin/tailwindcss -c tailwind.config.js \
 *            -i static/miniapp/css/tailwind.src.css \
 *            -o static/miniapp/css/tailwind.css --minify
 *  Consolidates the former inline window.tailwind.config blocks (home + CRM).
 */
const navy = {
  50: '#ECEDF4', 100: '#DFE1EC', 200: '#C3C7DC', 300: '#9CA3C6',
  400: '#5C6499', 500: '#1C2350', 600: '#161C44', 700: '#111634',
  800: '#0D1129', 900: '#090C1F',
};

module.exports = {
  // Must include the JS that emits utility classes in template strings,
  // or those classes get purged from the build.
  content: [
    './templates/**/*.html',
    './crm/templates/**/*.html',
    './static/miniapp/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        navy,
        rose: navy,            // back-compat: existing rose-* (esp. CRM) render navy
        gold: { 400: '#E0A636', 500: '#C98A1E' },
      },
      fontFamily: {
        sans: ['Geist', '-apple-system', 'BlinkMacSystemFont', 'Inter', 'system-ui', 'sans-serif'],
        display: ['Instrument Serif', 'Cormorant Garamond', 'Times New Roman', 'serif'],
        mono: ['Geist Mono', 'JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        glass: '0 25px 65px -25px rgba(15, 23, 42, 0.8)',
      },
    },
  },
  // First-party plugins are bundled in the standalone CLI (no npm install needed).
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
  ],
};
