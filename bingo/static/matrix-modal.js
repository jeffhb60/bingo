// A native dialog keeps the game on the same page while checking drawn calls.
// If JavaScript is unavailable, the trigger remains a link to the full matrix.
const matrixDialog = document.getElementById('call-matrix-dialog');
const matrixTrigger = document.querySelector('[data-open-matrix]');

if (matrixDialog && matrixTrigger && typeof matrixDialog.showModal === 'function') {
  matrixTrigger.addEventListener('click', (event) => {
    event.preventDefault();
    matrixDialog.showModal();
  });
  // Native <dialog> also closes on Escape, and method="dialog" handles the ×.
}