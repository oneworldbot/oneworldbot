document.getElementById('play-roulette').addEventListener('click', ()=>{
  const spin = Math.floor(Math.random()*37);
  document.getElementById('roulette-result').textContent = 'Spin: ' + spin;
});
