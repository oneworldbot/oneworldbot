document.getElementById('play-slots').addEventListener('click', ()=>{
  const symbols = ['🍒','🔔','🍋','⭐','7️⃣'];
  const r = [];
  for(let i=0;i<3;i++) r.push(symbols[Math.floor(Math.random()*symbols.length)]);
  const result = '|' + r.join('|') + '|';
  document.getElementById('slots-result').textContent = result;
  // demo: if user is authenticated, POST credit to bot server
  try{
    const userId = new URLSearchParams(window.location.search).get('user_id');
    if(userId){
      const origin = window.location.origin || (window.location.protocol + '//' + window.location.host)
      const url = origin + '/webapp/credit'
      fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id: parseInt(userId), amount: 10, secret: 'WEBAPP_SHARED_SECRET'})}).then(r=>r.json()).then(j=>console.log('credit response', j)).catch(e=>console.warn('credit failed',e));
    }
  }catch(e){console.warn(e)}
});
