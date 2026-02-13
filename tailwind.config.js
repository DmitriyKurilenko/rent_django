/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './boats/**/*.py',
    './accounts/**/*.py',
    './static/js/**/*.js'
  ],
  theme: {
    extend: {}
  },
  plugins: [require('@tailwindcss/typography'), require('daisyui')],
  daisyui: {
    themes: ['winter']
  }
};
