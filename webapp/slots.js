document.getElementById('play-slots').addEventListener('click', ()=>{
  const symbols = ['🍒','🔔','🍋','⭐','7️⃣'];
  const r = [];
  for(let i=0;i<3;i++) r.push(symbols[Math.floor(Math.random()*symbols.length)]);
  const result = '|' + r.join('|') + '|';
  document.getElementById('slots-result').textContent = result;
});
