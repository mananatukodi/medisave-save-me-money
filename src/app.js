const services = [
  ['✦', 'Ask MediSaveAI', 'Understand healthcare information safely.', 'assistant'],
  ['⌕', 'Find a doctor', 'Search verified listings and availability.', 'doctors'],
  ['⌂', 'Find a hospital', 'Compare services, access and details.', 'hospitals'],
  ['▤', 'Rooms & beds', 'Availability needs confirmation from the hospital.', 'beds'],
  ['✚', 'Ambulance', 'Find emergency transport details.', 'ambulance'],
  ['◌', 'Government schemes', 'Guidance from official sources.', 'schemes'],
  ['₹', 'Save money', 'Review bills and plan possible costs.', 'savings'],
  ['◒', 'Labs & tests', 'Find diagnostics and organize reports.', 'labs'],
];
const dialogCopy = {
  emergency: ['EMERGENCY SUPPORT', 'Get emergency help', 'For immediate danger or a medical emergency, call your local emergency number now. This demo will help you prepare a profile and locate verified services when connected.'],
  assistant: ['AI HEALTH ASSISTANT', 'How can I help you prepare?', 'I’m an AI assistant, not a doctor. I can explain healthcare information, help you prepare questions, and guide you to care. I cannot diagnose or prescribe.'],
  beds: ['ROOMS & BEDS', 'Availability needs confirmation', 'We only show current availability when a hospital reliably provides it. Contact the hospital to confirm a bed or room.'],
  schemes: ['GOVERNMENT SCHEMES', 'Verify eligibility officially', 'Scheme information is guidance only. Check the official scheme portal or a verified hospital for live eligibility and benefits.'],
  savings: ['SAVE MONEY', 'Review before you decide', 'We can help organize costs and questions. Potential savings and coverage are estimates, not guarantees.'],
  privacy: ['SETTINGS & PRIVACY', 'Your data, your control', 'Create a time-limited sharing permission, see access history, or revoke a recipient’s access. Your entire profile is never shared automatically.'],
  bill: ['MEDICAL BILL ANALYZER', 'Upload a bill for review', 'Bill analysis identifies line items that may need review and prepares questions for the billing desk. It does not determine whether charges are fraudulent or illegal.'],
  calculator: ['COST CALCULATOR', 'Plan your out-of-pocket cost', 'Estimate: total cost − insurance or scheme contribution − applicable assistance. We will label each input by its source and confidence.'],
};
const grid = document.querySelector('#serviceGrid');
services.forEach(([icon, title, copy, key], index) => {
  const button = document.createElement('button'); button.className = `service-card ${index === 0 ? 'featured' : ''}`;
  button.innerHTML = `<span class="service-icon">${icon}</span><span><strong>${title}</strong><small>${copy}</small></span><b>→</b>`;
  button.addEventListener('click', () => openDialog(key)); grid.append(button);
});
const dialog = document.querySelector('#actionDialog');
function openDialog(key) { const copy = dialogCopy[key] || ['MEDISAVEAI', key[0].toUpperCase()+key.slice(1), 'This service is part of the MediSaveAI care journey.']; document.querySelector('#dialogEyebrow').textContent=copy[0]; document.querySelector('#dialogTitle').textContent=copy[1]; document.querySelector('#dialogText').textContent=copy[2]; dialog.showModal(); }
document.querySelector('#emergencyButton').addEventListener('click', () => openDialog('emergency'));
document.querySelector('#assistantNav').addEventListener('click', (e) => {e.preventDefault(); openDialog('assistant')});
document.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',()=>openDialog(b.dataset.open)));
document.querySelector('.dialog-close').addEventListener('click',()=>dialog.close());
document.querySelector('#showAll').addEventListener('click',()=>{grid.classList.toggle('expanded'); document.querySelector('#showAll').innerHTML = grid.classList.contains('expanded') ? 'Show fewer services <span>↑</span>' : 'View all services <span>→</span>';});
document.querySelector('#care-search').addEventListener('input', e => { document.querySelector('#searchHint').textContent = e.target.value ? `Search ready for “${e.target.value}” — connect your secure search API to continue.` : 'Try “eye specialist”, “medical bill”, or “scheme eligibility”.'; });
document.querySelector('#languageButton').addEventListener('click', e=>{e.currentTarget.firstChild.textContent = e.currentTarget.textContent.includes('EN') ? 'తెలుగు ' : 'EN ';});
