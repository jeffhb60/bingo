const heading = document.getElementById('game_word');
if (heading) {
  const updateLabels = () => {
    const word = heading.value.toUpperCase();
    document.querySelectorAll('[data-column-letter]').forEach((element, index) => {
      element.textContent = /^[A-Z]{5}$/.test(word) ? word[index] : '–';
    });
  };
  heading.addEventListener('input', updateLabels);
  updateLabels();
}