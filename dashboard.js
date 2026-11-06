"use strict";

const $ = id => document.getElementById(id);
const sessionToken = document.querySelector('meta[name="jobflow-token"]').content;
const sample = new URLSearchParams(location.search).has("sample") || sessionToken.startsWith("__");
const paths = {
    brief:"M9 6V4h6v2M3 8h18v12H3zM3 12h18m-11 0v3h4v-3",home:"m3 11 9-8 9 8M5 10v11h5v-7h4v7h5V10",
    bookmark:"M6 3h12v18l-6-5-6 5z",layers:"m3 8 9-5 9 5-9 5zm0 4 9 5 9-5M3 16l9 5 9-5",
    user:"M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM3 22a9 7 0 0 1 18 0z",
    settings:"M12 2v4m0 12v4M2 12h4m12 0h4M5 5l3 3m8 8 3 3M5 19l3-3m8-8 3-3M18 12a6 6 0 1 1-12 0 6 6 0 0 1 12 0z",
    calendar:"M3 5h18v16H3zM7 2v6m10-6v6M3 10h18",send:"m22 2-7 20-4-9-9-4 20-7zM11 13 22 2",
    clock:"M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0zM12 6v6l4 2",
    refresh:"M20 7A9 9 0 0 0 4 7l-1 4m0-6v6h6m-5 6a9 9 0 0 0 16 0l1-4m0 6v-6h-6",
    search:"M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0zm-2 5 6 6",list:"M4 6h16M4 12h16M4 18h16",
    grid:"M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z",warehouse:"m2 8 10-6 10 6v13H2zm4 2h12v11M6 14h12m-12 3h12",
    kitchen:"M4 2v7a3 3 0 0 0 6 0V2M7 2v20M18 2c-3 4-4 8-4 11h4m0-11v20",clean:"m15 3 6 6-9 9-6-6zm-9 9-4 4 6 6 4-4",
    factory:"M3 21V9l6 4V8l6 4V4h5v17zM7 17h1m4 0h1m4 0h1",box:"m3 7 9-4 9 4v10l-9 4-9-4zm0 0 9 4 9-4m-9 4v10",
    mail:"M2 5h20v14H2zM2 6l10 8 10-8",link:"M14 3h7v7m0-7-9 9m-3-7H3v16h16v-6",pin:"M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0zM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"
};
const categories = {warehouse:"Warehouse", cleaning:"Cleaning", food_service:"Food Service", production:"Production",
    site_work:"Site Work", delivery:"Delivery", retail_stock:"Retail Stock", port:"Port", moving:"Moving",
    events:"Events", outdoor:"Outdoor", vehicle_care:"Vehicle Care"};
const roleIcons = {warehouse:"warehouse", cleaning:"clean", food_service:"kitchen", production:"factory"};
const statusNames = {draft:sample?"Good Match":"By Email", portal:"Apply Online", review:"Needs Review", skip:"Outside Criteria", held:"On Hold", sent:"Sent"};
const views = {discover:"Discover Jobs", saved:"Saved Jobs", applications:"Applications"};
const sampleRows = [
    ["warehouse","Warehouse Worker","LogiPro Oy","Vantaa","Full-time","English friendly","Posted 2 days ago","draft",
     "Packing, sorting and preparing orders, loading and unloading deliveries, and keeping the warehouse tidy.",
     ["Team player and reliable","Basic Finnish is a plus (not required)","Able to do physical work","Previous warehouse experience is an advantage"]],
    ["food_service","Kitchen Assistant","Ravintola Bistro","Helsinki","Part-time","English + Finnish","Posted 3 days ago","review",
     "Support food preparation, clean the kitchen and help the service team during busy shifts.",["Confirm the required Finnish level","Hygiene Passport requested"]],
    ["cleaning","Cleaner","Siivouspalvelu Clean & Co","Espoo","Part-time","Finnish helpful","Posted 6 hours ago","draft",
     "Clean offices and shared areas on an evening shift.",["English is accepted","Attention to detail"]],
    ["production","Production Worker","TeknoManufacturing Oy","Vantaa","Full-time","English friendly","Posted 4 days ago","portal",
     "Pack finished products and follow the production line safety procedures.",["Work safely around machinery","Apply through the employer’s portal"]]
].map(([category,title,company,city,contract,lang,posted,status,description,requirements],index) => ({
    id:"sample-"+index, category,title,company,cities:[city],contract,lang,posted,status,description,requirements,
    published_at:Math.floor(Date.now()/1000)-[48,72,6,96][index]*3600,
    assessment:{fit:status==="draft"?"ready":status==="portal"?"online":"check", priority:status==="draft"?2:0},
    english:status!=="review", reason:status==="draft" ? "The worksite is in your target area and English is accepted."
        : status==="portal" ? "This employer takes applications through its online form." : "Confirm the employer’s Finnish requirement.",
    application:status==="draft" ? "The employer accepts applications by email." : "Check the original advertisement for application instructions.",
    recipient:status==="draft" ? "hiring@example.com" : null, attachment:"Example CV.pdf"
}));

function node(tag,text,style) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (style) element.className = style;
    return element;
}
function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
    svg.setAttribute("viewBox","0 0 24 24"); svg.setAttribute("class","ico");
    svg.setAttribute("fill","none"); svg.setAttribute("stroke","currentColor"); svg.setAttribute("stroke-width","1.7");
    svg.setAttribute("stroke-linecap","round"); svg.setAttribute("stroke-linejoin","round"); svg.setAttribute("aria-hidden","true");
    const path = document.createElementNS(svg.namespaceURI,"path");
    path.setAttribute("d",paths[name] || paths.box); svg.append(path); return svg;
}
for (const element of document.querySelectorAll("[data-icon]")) element.append(icon(element.dataset.icon));
function button(text, handler, style, glyph) {
    const b = node("button",undefined,style); b.type="button";
    if (glyph) b.append(icon(glyph));
    if (text) b.append(document.createTextNode(text));
    b.addEventListener("click",handler); return b;
}
function option(value,label) { const item=node("option",label); item.value=value; return item; }
for (const [key,label] of Object.entries(categories)) $("category").append(option(key,label));
let gmailSaved=false, gmailSender="";
let deliveryProgress=null, sendDelay=[30,90], submittingBatch=false;

function duration(seconds) {
    if(seconds<60) return Math.ceil(seconds)+"s";
    const minutes=Math.ceil(seconds/60);
    return minutes<60 ? minutes+"m" : Math.floor(minutes/60)+"h "+minutes%60+"m";
}

function renderDelivery() {
    $("delivery-progress").hidden=!deliveryProgress;
    if(!deliveryProgress) return;
    const {state:phase,total,sent,processed,next_at:next}=deliveryProgress;
    const finished=phase==="finished" || phase==="stopped";
    $("delivery-progress").classList.toggle("finished",finished);
    $("delivery-title").textContent=phase==="submitting"?"Starting batch":
        phase==="checking"?"Checking "+total+" applications":
        phase==="connecting"?"Connecting to Gmail":
        (phase==="stopped"?"Batch stopped · ":"")+sent+" of "+total+" sent";
    $("delivery-meter").max=Math.max(1,total);
    if(["submitting","checking","connecting"].includes(phase)) $("delivery-meter").removeAttribute("value");
    else $("delivery-meter").value=processed;
    let message=deliveryProgress.message || "";
    if(phase==="submitting") message="Starting delivery for "+total+" selected applications…";
    else if(phase==="checking") message="Checking the selected listings before contacting Gmail…";
    else if(phase==="finished" && !message) message=sent===total?"Batch finished":"Batch finished. Check unsent jobs.";
    else if(phase==="waiting") {
        const seconds=Math.max(0,next-Date.now()/1000);
        const gaps=Math.max(0,total-processed-1);
        const left=Math.ceil(seconds);
        message="Next in "+(left>=60 ? Math.floor(left/60)+"m "+left%60+"s" : left+"s");
        if(gaps) message+=" · about "+duration(seconds+gaps*sendDelay[0])+"–"+duration(seconds+gaps*sendDelay[1])+" left";
    } else if(phase==="sending") message="Gmail is processing the batch…";
    $("delivery-timing").textContent=message;
}
setInterval(()=>{if(deliveryProgress?.state==="waiting")renderDelivery();},1000);
let startingCollection=false, generalTemplate=false;
let infinity=false, delivering=false;
const state = {rows:sample?sampleRows:[], view:"discover", active:sample?sampleRows[0].id:null, tab:"details", grid:false,
    limit:35, completed:0, saved:new Set(), checked:new Set(), choices:new Map(), mode:"idle", revision:-1};
let visibleRows=[], detailRequest=0, toastTimer, confirmed=[];
function toast(message) {
    $("toast").textContent=message; $("toast").hidden=false; clearTimeout(toastTimer);
    toastTimer=setTimeout(()=>$("toast").hidden=true,5000);
}
function updateChoice(job) { return state.choices.get(job.id) || {template:"auto",language:"auto"}; }
function sampleDraft(job, choice) {
    const role=categories[choice.template] || job.title;
    return choice.language==="fi" ? {subject:"Hakemus – "+job.title,body:"Hei,\n\nHaen tehtävää "+job.title+". Olen kiinnostunut käytännön työstä ja tiiminne työtavoista.\n\nAnsioluetteloni on liitteenä.\n\nYstävällisin terveisin,\nHakija"}
        : {subject:"Application – "+job.title,body:"Hello,\n\nI’m applying for the "+job.title+" position. I’d welcome the opportunity to support your team with "+role.toLowerCase()+" duties.\n\nMy CV is attached.\n\nKind regards,\nApplicant"};
}
let exampleTemplates;
async function loadTemplateExamples() {
    if(!sessionToken.startsWith("__")) {
        const response=await fetch("/api/templates",{headers:{"X-JobBot-Token":sessionToken}});
        if(response.ok) return response.json();
    }
    return Object.fromEntries(Object.keys(categories).map(key=>[key,Object.fromEntries(
        ["en","fi"].map(lang=>{const example=sampleDraft({title:"Example position"},{template:key,language:lang});
            return [lang,[example.subject,example.body]];})
    )]));
}
const api = {
    collect:async()=>toast("Sample vacancies are already loaded."),
    infinity:async()=>toast("Scrape Jobs is available in the live dashboard."),
    stop:async()=>{}, bookmark:async()=>{}, profile:async()=>toast("Profile editing is available in the live dashboard."),
    reload:async()=>toast("Sample profile refreshed."),
    detail:async job=>job,
    draft:async(job,choice)=>{
        const key=choice.template==="auto" ? job.category : choice.template;
        const pair=(await api.templateExamples())[key]?.[choice.language==="fi"?"fi":"en"];
        return pair ? {subject:pair[0].replace("Example position",job.title),
            body:pair[1].replace("Example position",job.title)} : sampleDraft(job,choice);
    },
    templateExamples:async()=>exampleTemplates ||= await loadTemplateExamples(),
    markApplied:async id=>{
        state.rows=state.rows.filter(job=>job.id!==id);
        state.completed++;
    },
    send:async ids=>{
        state.rows=state.rows.filter(job=>!ids.includes(job.id));
        state.completed+=ids.length;
        toast("Sample approval recorded. No email was sent.");
    }
};
const row = id => state.rows.find(job=>job.id===id);
const city = job => job.cities.filter(Boolean).join(", ") || "Unconfirmed";
const eligible = job => job?.status==="draft" && Boolean(job.recipient);
const hasEmail = job => eligible(job) || Boolean(job?.contact_count);
const fitLabels={ready:"Good fit",check:"Check first",online:"Apply online",outside:"Outside preferences"};
function suggestedJobs() {
    return state.rows.filter(job=>eligible(job) && (sample || job.batch_recipient) && job.assessment?.fit==="ready").sort((a,b)=>
        b.assessment.priority-a.assessment.priority ||
        (b.published_at || 0)-(a.published_at || 0) ||
        (a.deadline_days ?? Infinity)-(b.deadline_days ?? Infinity));
}
const chip = (text,style) => node("span",text,"chip"+(style ? " "+style : ""));
function statusChip(job) { return chip(statusNames[job.status] || "Needs Review",job.status==="draft" ? "good" : job.status==="review" ? "warn" : ""); }
function guard(task) { return async (...args)=>{ try { await task(...args); } catch(error) { toast(error.message); } }; }
async function save(ids) {
    const mark=ids.some(id=>!state.saved.has(id));
    await api.bookmark(ids,mark);
    for (const id of ids) { if(mark) state.saved.add(id); else state.saved.delete(id); }
    render();
}
function bookmark(job) {
    const saved=state.saved.has(job.id);
    const b=button(null,guard(()=>save([job.id])),"icon-button bookmark"+(saved?" saved":""),"bookmark");
    b.title=saved?"Remove saved job":"Save job"; b.setAttribute("aria-label",b.title); b.setAttribute("aria-pressed",String(saved));
    return b;
}
function check(job,value) {
    if(value) state.checked.add(job.id); else state.checked.delete(job.id);
    updateStats();
}
function updateStats() {
    const applicable=visibleRows;
    const selected=[...state.checked];
    $("total").textContent=state.rows.length;
    $("saved-count").textContent=state.saved.size;
    $("sent-count").textContent=state.completed;
    $("pending-count").textContent=state.rows.filter(job=>["review","draft","held"].includes(job.status)).length;
    $("application-count").textContent=state.rows.filter(job=>["draft","sent","held","portal"].includes(job.status)).length;
    $("selected-count").textContent=selected.length ? selected.length+" selected" : "Select all (0)";
    $("select-all").checked=applicable.length>0 && applicable.every(job=>state.checked.has(job.id));
    $("select-all").disabled=!applicable.length;
    $("save-selected").disabled=!selected.length;
    const ready=selected.filter(id=>eligible(row(id))).length;
    $("batch").disabled=!selected.length || delivering || state.mode==="delivery";
    const suggested=suggestedJobs().length;
    $("suggested-count").textContent=suggested;
    $("suggested").disabled=!suggested || delivering || state.mode==="delivery";
    $("email-batch").disabled=!state.rows.some(job=>job.batch_recipient) || delivering || state.mode==="delivery";
    $("selection-note").textContent=selected.length
        ? ready+" of "+selected.length+" selected can be emailed. "+(ready<selected.length?"Use the employer’s form or review the reason on the remaining jobs.":"")
        : visibleRows.some(eligible)?"Select jobs to prepare one email batch.":"No visible jobs currently accept verified email applications. You can still select and save them.";
    $("collect").disabled=startingCollection || infinity || state.mode!=="idle";
    $("infinity").disabled=startingCollection || infinity || state.mode!=="idle";
    $("collect").lastChild.textContent=startingCollection?"Starting…":state.mode==="collection"?"Collecting…":"Collect Jobs";
    $("stop").hidden=state.mode!=="collection" && !infinity;
    $("progress").hidden=state.mode!=="collection";
}
const postedDate=new Intl.DateTimeFormat("en-FI",{dateStyle:"medium",timeZone:"Europe/Helsinki"});
function postedLabel(job) {
    return job.posted || (job.published_at ? "Posted "+postedDate.format(new Date(job.published_at*1000)) : "");
}
function render(preserveDetail=false) {
    const needle=$("query").value.trim().toLowerCase();
    const where=$("location").value, language=$("language").value, category=$("category").value;
    const contract=$("contract").value, status=$("status").value;
    const now=Date.now()/1000;
    visibleRows=state.rows.filter(job=>
        (!$("last24").checked || (job.published_at>now-86400 && job.published_at<=now)) &&
        (state.view!=="saved" || state.saved.has(job.id)) &&
        (state.view!=="applications" || ["draft","portal","held","sent"].includes(job.status)) &&
        (!where || (where==="unknown" ? !job.cities.some(Boolean) : job.cities.includes(where))) &&
        (language!=="english" || job.english) && (!category || job.category===category) &&
        (!contract || (job.contract || "Unknown")===contract) && (!status || (status==="email" ? (sample ? hasEmail(job) : Boolean(job.batch_recipient)) : job.status===status)) &&
        (!needle || [job.title,job.company,city(job),categories[job.category]].join(" ").toLowerCase().includes(needle)));
    if($("sort").value==="title") visibleRows.sort((a,b)=>a.title.localeCompare(b.title));
    else if($("sort").value==="recent") visibleRows.sort((a,b)=>(b.published_at || 0)-(a.published_at || 0));
    else if (!sample) visibleRows.sort((a,b)=>Number(b.english)-Number(a.english) || Number(eligible(b))-Number(eligible(a)));
    if (!visibleRows.some(job=>job.id===state.active)) {
        state.active=visibleRows[0]?.id; state.tab="details"; preserveDetail=false;
    }
    $("heading").textContent=views[state.view];
    $("subtitle").textContent=sample ? "Sample vacancies · Explore the layout and application workflow." :
        "Find, review and apply to suitable jobs in Finland.";
    for(const control of document.querySelectorAll("[data-view]")) control.classList.toggle("current",control.dataset.view===state.view);
    $("found").textContent=visibleRows.length+" jobs found"; $("email-only").setAttribute("aria-pressed",String($("status").value==="email"));
    $("jobs").classList.toggle("grid",state.grid);
    $("list-view").classList.toggle("active",!state.grid); $("grid-view").classList.toggle("active",state.grid);
    $("show-more").hidden=visibleRows.length<=state.limit;
    const cards=visibleRows.slice(0,state.limit).map(job=>{
        const card=node("article",undefined,"job"+(job.id===state.active?" active":""));
        const checkbox=node("input"); checkbox.type="checkbox";
        checkbox.checked=state.checked.has(job.id); checkbox.setAttribute("aria-label","Select "+job.title);
        checkbox.onchange=()=>check(job,checkbox.checked);
        const open=button(null,()=>{state.active=job.id;state.tab=eligible(job)?"draft":"details";render();},"job-main");
        const tile=node("span",undefined,"tile"); tile.append(icon(roleIcons[job.category] || "box"));
        const text=node("div"); text.append(node("strong",job.title),node("span",[job.company,city(job)].filter(Boolean).join(" · "),"meta"));
        if(postedLabel(job)) text.append(node("span",postedLabel(job),"meta"));
        const chips=node("div",undefined,"chips");
        chips.append(statusChip(job));
        if(job.assessment) chips.append(chip(fitLabels[job.assessment.fit],job.assessment.fit==="ready"?"good":job.assessment.fit==="check"?"warn":""));
        if(categories[job.category]) chips.append(chip(categories[job.category]));
        if(job.contract) chips.append(chip(job.contract));
        chips.append(chip(job.lang || (job.english?"English confirmed":"Language to verify"),"lang"));
        text.append(chips);open.append(tile,text);card.append(checkbox,open,bookmark(job));return card;
    });
    $("jobs").replaceChildren(...(cards.length?cards:[node("p",state.mode==="collection"?"Collection is running. Jobs will appear as they arrive.":"No jobs match this view. Clear filters or collect jobs.","empty")]));
    updateStats();
    if(!preserveDetail) renderDetail();
}
function original(job,text) {
    if (!job.url) return button(text,()=>toast("This is a sample vacancy."),null,"link");
    const link=node("a"); link.href=text==="Open Application Form" ? (job.application_url || job.url) : job.url; link.target="_blank"; link.rel="noopener noreferrer";
    link.append(icon("link"),document.createTextNode(text));return link;
}
function facts(job) {
    const list=node("dl",undefined,"facts");
    for(const [key,value] of [["Location",city(job)],["Contract",job.contract || "Unconfirmed"],
        ["Work language",job.lang || (job.english?"English confirmed":"Unconfirmed")],
        ["Application method",eligible(job)?"By email":job.status==="portal"?"Online form":"Check listing"],["Deadline",job.deadline]]) {
        if(value) list.append(node("dt",key),node("dd",value));
    } return list;
}
async function renderDetail() {
    const request=++detailRequest, job=row(state.active), panel=$("review");
    if(!job) {panel.replaceChildren(node("p","Select a job to see its details and application route.","empty"));return;}
    const head=node("div",undefined,"review-head"), tile=node("span",undefined,"tile");tile.append(icon("box"));
    const title=node("div");title.append(node("h2",job.title),node("div",job.company || job.source || "","meta"),
        node("div",city(job),"meta"));
    if(postedLabel(job)) title.append(node("div",postedLabel(job),"meta"));
    const badges=node("div",undefined,"badge-area");badges.append(statusChip(job),bookmark(job));head.append(tile,title,badges);
    const tabs=node("div",undefined,"tabs");
    for(const [key,label] of Object.entries({details:"Job Details",application:"Application",draft:"Draft Message"}))
        tabs.append(button(label,()=>{state.tab=key;renderDetail();},state.tab===key?"active":""));
    const body=node("div",undefined,"review-body"), actions=node("div",undefined,"review-actions");
    if(eligible(job)) actions.append(button("Apply by Email",guard(()=>reviewBatch([job.id])),"primary","mail"));
    else {
        if(job.status==="portal") actions.append(original(job,"Open Application Form"));
        if(!sample && hasEmail(job)) actions.append(button("Email this job",guard(()=>reviewBatch([job.id],job.id)),null,"mail"));
    }
    const saveButton=button(state.saved.has(job.id)?"Remove Saved Job":"Save Job",guard(()=>save([job.id])),null,"bookmark");
    actions.append(saveButton,original(job,"Open Original Ad"));
panel.replaceChildren(head,tabs,body,actions);
    body.textContent="Loading listing…";
    try {
        const detail=await api.detail(job);
        if(request!==detailRequest) return;
        body.replaceChildren();
        if(state.tab==="details") {
            const grid=node("div",undefined,"review-grid"), copy=node("div");
            const description=detail.description || "Read the original advertisement.";
            const summary=sample ? description : description.replace(/^[\s\S]*?^\s*(?:Työn kuvaus|Työpaikan kuvaus|Job description)\s*$/mi,"").trim();
            const text=summary || description;
            const short=text.length>420 ? text.slice(0,420).replace(/\s+\S*$/,"")+"…" : text;
            copy.append(node("h3","Job description"),node("p",short,"description"));
            if(!sample && (short!==description)) {
                const more=node("details");
                more.append(node("summary","Read full original description"),node("p",description,"description"));
                copy.append(more);
            }
            if(detail.requirements?.length) {
                const list=node("ul"); for(const requirement of detail.requirements) list.append(node("li",requirement));
                copy.append(node("h3","Key requirements"),list);
            }
            grid.append(copy,facts(job));
            const match=node("div",undefined,"match"+(eligible(job)?" good":""));
            match.append(node("strong",job.assessment ? fitLabels[job.assessment.fit] : eligible(job)?(sample?"Your match: Good":"Review before applying"):"Application review"),
                node("p",job.assessment?.reason || job.reason));
            if(job.assessment?.evidence) match.append(node("p",job.assessment.evidence));
            body.append(grid,match);
        } else if(state.tab==="application") {
            body.append(node("h3","How to apply"),node("p",detail.application || "Follow the instructions in the original advertisement.","description"),facts(job));
        } else if(!eligible(job)) {
            body.append(node("p","An email draft is available only for listings that explicitly accept email applications."));
        } else {
            const controls=node("div",undefined,"draft-controls"), template=node("select"), language=node("select"), output=node("div",undefined,"draft-box");
            template.setAttribute("aria-label","Email template");language.setAttribute("aria-label","Email language");
            template.append(option("auto","Recommended template"),option("general","General experience"),...Object.entries(categories).map(([key,label])=>option(key,label)));
            language.append(option("auto","Employer preference"),option("en","English"),option("fi","Finnish"));
            let chosen=updateChoice(job);template.value=chosen.template;language.value=chosen.language;
            let version=0;
            async function preview(change) {
                const current=++version, proposed={template:template.value,language:language.value};
                try {
                    const message=await api.draft(job,proposed);
                    if(current!==version) return;
                    if(change){state.choices.set(job.id,proposed); chosen=proposed;check(job,false);render(true);}
                    output.textContent="To: "+job.recipient+"\nSubject: "+message.subject+"\nCV: "+(message.attachment || job.attachment || "Local profile CV")+"\n\n"+message.body;
                } catch(error) {
                    if(current!==version) return;
                    template.value=chosen.template;language.value=chosen.language;toast(error.message);
                }
            }
            template.onchange=()=>preview(true);language.onchange=()=>preview(true);controls.append(template,language);
            body.append(node("h3","Draft Message"),controls,output);preview(false);
        }
    } catch(error) { if(request===detailRequest) body.textContent=error.message; }
}
async function markApplied(job) {
    if(!window.confirm("Have you already submitted an application for "+job.title+"? This removes it from the active queue.")) return;
    const result=await api.markApplied(job.id);
    if(result) state.revision=result.revision;
    state.checked.delete(job.id);
    state.saved.delete(job.id);
    state.rows=state.rows.filter(item=>item.id!==job.id);
    render();
    if($("confirm").open) {
        if(state.checked.size) await reviewBatch([...state.checked]);
        else $("confirm").close();
    }
    toast("Marked as applied.");
}

async function reviewBatch(ids, manualId=null, broad=false, suggested=false, localBatch=false) {
    if(delivering || state.mode==="delivery") throw new Error("An email batch is already being sent.");
    const selected=ids.map(row).filter(Boolean);
    const jobs=selected.filter(job=>localBatch ? Boolean(job.batch_recipient) :
        eligible(job) || job.id===manualId || (broad && hasEmail(job)));
    const otherJobs=selected.filter(job=>!jobs.includes(job));
    const snapshot=state.revision, choices=Object.fromEntries(jobs.map(job=>[
        job.id,localBatch ? {template:"auto",language:"auto"} : broad && !suggested ? {template:"general",language:"auto"} : updateChoice(job)
    ]));
    const drafts=[];
    for(let index=0;!localBatch && index<jobs.length;index+=8) {
        drafts.push(...await Promise.all(jobs.slice(index,index+8).map(job=>api.draft(job,choices[job.id]))));
    }
    confirmed={ids:jobs.map(job=>job.id),revision:snapshot,versions:Object.fromEntries(jobs.map(job=>[job.id,job.version])),choices,manualId,broad,localBatch,recipients:{},included:new Set(jobs.map(job=>job.id))};
    $("manual-label").hidden=!manualId;
    const recipient=$("manual-recipient"), context=$("contact-context");
    recipient.required=Boolean(manualId);
    recipient.replaceChildren();
    context.hidden=!manualId;
    if(manualId) {
        const detail=await api.detail(row(manualId));
        const contacts=Object.entries(detail.contacts || {});
        if(!contacts.length) throw new Error("No published email was found for this job.");
        recipient.append(...contacts.map(([address])=>option(address,address)));
        recipient.onchange=()=>{context.textContent=detail.contacts[recipient.value] || "";};
        recipient.onchange();
    }
    $("confirm-note").textContent=sample?"This is a sample. Approval only updates the demo.":"Review the recipient, message and CV before approving delivery.";
    $("saved-gmail").hidden=sample || !jobs.length || !gmailSaved;
    $("saved-gmail").textContent=gmailSaved?"Sending from "+gmailSender:"";
    if(gmailSaved) $("sender").value=gmailSender;
    $("password-label").hidden=sample || !jobs.length || gmailSaved;
    $("sender-label").hidden=sample || !jobs.length || gmailSaved;
    $("sender").required=!sample && !gmailSaved && jobs.length>0;
    $("send-confirm").hidden=!jobs.length;
    if(manualId) $("confirm-note").textContent="Choose a published address. Check its context and the employer’s application route before sending.";
    if(broad) $("confirm-note").textContent=jobs.length+" jobs with published email addresses. Review the recipient for each and uncheck any you want to skip.";
    if(!jobs.length) $("confirm-note").textContent="None of these jobs can be emailed. Open the employer’s instructions or switch to email-ready jobs.";
    if(suggested) $("confirm-note").textContent=jobs.length+" role-matched applications are ready. Approve the batch here, or expand any job to inspect its draft.";
    if(localBatch) $("confirm-note").textContent=jobs.length+" jobs with confirmed worksites in Helsinki, Espoo, or Vantaa. JobFlow picked one published address per job.";
    function updateSendLabel() {
        const count=confirmed.included.size;
        $("send-confirm").textContent=suggested ? "Send "+count+(count===1?" application":" applications") : "Approve and send";
        const gaps=Math.max(0,count-1);
        $("send-estimate").hidden=sample || !gaps;
        $("send-estimate").textContent=gaps ? "Scheduled gaps: about "+duration(gaps*sendDelay[0])+"–"+
            duration(gaps*sendDelay[1])+", plus listing checks and Gmail delivery. " : "";
    }
    updateSendLabel();
    if(!sample && jobs.length>1) $("confirm-note").textContent+=" Messages are spaced "+sendDelay[0]+"–"+sendDelay[1]+" seconds apart.";
    const recipientCounts=new Map();
    for(const job of jobs) {
        const address=localBatch ? job.batch_recipient : job.recipient;
        if(address) recipientCounts.set(address,(recipientCounts.get(address) || 0)+1);
    }
    const shared=[...recipientCounts.values()].some(count=>count>1);
    $("shared-recipient").hidden=!shared;
    $("shared-recipient").textContent=shared?"Some selected jobs share a recipient. Check whether you want to send a separate application for each vacancy.":"";
    let updating=0;
    $("send-confirm").disabled=false;
    $("batch-review").replaceChildren(...jobs.map((job,index)=>{
        const section=node("details"), message=drafts[index];
        section.open=!localBatch && jobs.length===1;
        const output=node("div",undefined,"draft-box");
        const show=message=>{output.textContent="Subject: "+message.subject+"\nCV: "+(message.attachment || job.attachment || "Local profile CV")+"\n\n"+message.body;};
        if(message) show(message);
        else {
            output.textContent="Open this row to see the draft.";
            section.addEventListener("toggle",guard(async()=>{
                if(section.open && output.textContent==="Open this row to see the draft.") {
                    show(await api.draft(job,choices[job.id]));
                }
            }));
        }
        const options=node("div",undefined,"draft-controls"), template=node("select"), language=node("select");
        template.setAttribute("aria-label","Template for "+job.title);
        language.setAttribute("aria-label","Language for "+job.title);
        template.append(option("auto","Recommended template"),option("general","General experience"),...Object.entries(categories).map(([key,label])=>option(key,label)));
        language.append(option("auto","Employer preference"),option("en","English"),option("fi","Finnish"));
        template.value=choices[job.id].template; language.value=choices[job.id].language;
        const change=guard(async()=>{
            const chosen={template:template.value,language:language.value};
            updating++;
            $("send-confirm").disabled=true;
            template.disabled=language.disabled=true;
            try {
                const preview=await api.draft(job,chosen);
                choices[job.id]=chosen;
                state.choices.set(job.id,chosen);
                show(preview);
            } finally {
                template.value=choices[job.id].template;
                language.value=choices[job.id].language;
                template.disabled=language.disabled=false;
                $("send-confirm").disabled=--updating>0;
            }
        });
        template.onchange=language.onchange=change;
        options.append(template,language);
        const summary=node("summary",job.title+(localBatch?" · "+job.batch_recipient:job.recipient?" · "+job.recipient:broad?" · Published contacts":" · Choose recipient above"));
        section.append(summary,options,output);
        if(broad || suggested) {
            const include=node("input");
            include.type="checkbox";
            include.checked=true;
            include.setAttribute("aria-label","Include "+job.title);
            const label=node("label");
            label.append(include,document.createTextNode(" Include in this batch"));
            section.insertBefore(label,options);
            let recipient;
            if(!localBatch && !eligible(job)) {
                const contacts=Object.entries(message.contacts || {});
                recipient=node("select");
                recipient.setAttribute("aria-label","Published address for "+job.title);
                if(contacts.length!==1) recipient.append(option("","Choose a published address"));
                for(const [address,context] of contacts) {
                    const item=option(address,address);
                    item.title=context;
                    recipient.append(item);
                }
                recipient.required=true;
                const info=node("p");
                function updateRecipient() {
                    confirmed.recipients[job.id]=recipient.value;
                    info.textContent=message.contacts?.[recipient.value] || "";
                    summary.textContent=job.title+" · "+(recipient.value || "Choose a published address");
                }
                recipient.onchange=updateRecipient;
                updateRecipient();
                const addressLabel=node("label","Published recipient");
                addressLabel.append(recipient);
                section.insertBefore(addressLabel,options);
                section.insertBefore(info,options);
                if(suggested) section.insertBefore(node("p",job.reason),options);
                if(contacts.length!==1) section.open=true;
            }
            include.onchange=()=>{
                if(include.checked) confirmed.included.add(job.id);
                else confirmed.included.delete(job.id);
                if(recipient) recipient.disabled=!include.checked;
                updateSendLabel();
            };
        }
        if(!sample) section.append(button("Open attached CV",guard(()=>api.openCv({job:job.id})),null,"brief"));
        if(suggested) {
            const wrapper=node("div",undefined,"suggested-item");
            const include=section.querySelector('input[type="checkbox"]')?.parentElement;
            if(include) wrapper.append(include);
            wrapper.append(section);
            return wrapper;
        }
        return section;
    }));
    if(!jobs.length) $("batch-review").append(button("Show email-ready jobs",()=>{
        $("confirm").close();
        state.view="discover";
        state.checked.clear();
        for(const id of ["query","location","category","contract"]) $(id).value="";
        $("language").value="priority";
        $("status").value="email";
        render();
    },"primary","mail"));
    for(const job of otherJobs) {
        const section=node("div",undefined,"draft-box");
        section.append(node("strong",job.title),node("p",job.reason),
            original(job,job.status==="portal"?"Open Application Form":"Open Original Ad"));
        if(!sample && hasEmail(job)) section.append(button("Email this job",guard(()=>reviewBatch([job.id],job.id))));
        if(["portal","review"].includes(job.status)) {
            section.append(button("Mark as applied",guard(()=>markApplied(job))));
        }
        $("batch-review").append(section);
    }
    if(!$("confirm").open) $("confirm").showModal();
}
for(const b of document.querySelectorAll("[data-view]")) b.onclick=()=>{state.view=b.dataset.view;state.limit=35;render();};
for(const b of document.querySelectorAll("[data-close]")) b.onclick=()=>$(b.dataset.close).close();
for(const id of ["query","location","language","category","sort","status","contract"]) $(id).oninput=()=>{state.limit=35;render();};
$("last24").onchange=()=>{
    if($("last24").checked) $("sort").value="recent";
    state.limit=35;
    render();
};
setInterval(()=>{if($("last24").checked)render(true);},60000);
$("list-view").onclick=()=>{state.grid=false;render(true);};$("grid-view").onclick=()=>{state.grid=true;render(true);};
$("show-more").onclick=()=>{state.limit+=35;render(true);};
$("select-all").onchange=()=>{const value=$("select-all").checked; for(const job of visibleRows) check(job,value);render(true);};
$("save-selected").onclick=guard(()=>save([...state.checked]));
$("batch").onclick=guard(()=>reviewBatch([...state.checked]));
$("email-batch").onclick=guard(async()=>{
    const ids=state.rows.filter(job=>job.batch_recipient).map(job=>job.id);
    $("email-batch").disabled=true;
    try {await reviewBatch(ids,null,true,true,true);}
    finally {updateStats();}
});
$("suggested").onclick=guard(async()=>{
    const ids=suggestedJobs().map(job=>job.id);
    $("suggested").disabled=true;
    try {await reviewBatch(ids,null,false,true);}
    finally {updateStats();}
});
$("desperate").onclick=guard(async()=>{
    if(!sample && !generalTemplate) throw new Error("Close the old JobFlow terminal and reopen the launcher to use Desperate Mode.");
    const ids=state.rows.filter(job=>hasEmail(job) && !["held","sent"].includes(job.status)).map(job=>job.id);
    if(!ids.length) throw new Error("No jobs with published email addresses are available yet.");
    $("desperate").disabled=true;
    toast("Preparing "+ids.length+" drafts for Desperate Mode…");
    try {await reviewBatch(ids,null,true);}
    finally {$("desperate").disabled=false;}
});
$("search-form").onsubmit=guard(async event=>{
    event.preventDefault();
    if(startingCollection || state.mode!=="idle") return;
    startingCollection=true;
    updateStats();
    try {
        await api.collect();
        if(!sample) {
            $("toast").hidden=true;
            $("query").value="";
            render();
        }
    } finally {
        startingCollection=false;
        updateStats();
    }
});
$("infinity").onclick=guard(async()=>{
    startingCollection=true;
    updateStats();
    try { await api.infinity(); if(!sample) infinity=true; }
    finally { startingCollection=false;updateStats(); }
});
$("stop").onclick=guard(()=>api.stop());
$("gmail-open").disabled=sample;
$("gmail-open").onclick=()=>{
    $("gmail-address").value=gmailSender || $("sender").value;
    $("gmail-forget").hidden=!gmailSaved;
    $("gmail").showModal();
};
$("gmail").onclose=()=>$("gmail-password").value="";
$("gmail-form").onsubmit=guard(async event=>{
    event.preventDefault();
    const sender=$("gmail-address").value.trim();
    const password=$("gmail-password").value;
    await api.saveGmail(sender,password);
    gmailSaved=true;
    gmailSender=sender;
    $("gmail").close();
    toast("Gmail saved on this PC.");
});
$("gmail-forget").onclick=guard(async()=>{
    await api.forgetGmail();
    gmailSaved=false;
    gmailSender="";
    $("gmail").close();
    toast("Saved Gmail removed.");
});
$("profile-open").onclick=guard(async()=>{
    $("profile").showModal();
    const list=$("profile-cvs");
    list.replaceChildren(node("p",sample?"Sample CV is used in preview.":"Loading configured CVs…"));
    if(sample) return;
    const cvs=await api.cvs();
    list.replaceChildren(...cvs.map(cv=>{
        const entry=node("p", (categories[cv.role] || "Default CV")+": "+cv.name+" ");
        if(cv.available) entry.append(button("Open PDF",guard(()=>api.openCv({role:cv.role}))));
        else entry.append(document.createTextNode("(file missing)"));
        return entry;
    }));
});$("edit-profile").onclick=guard(()=>api.profile());
$("reload-profile").onclick=guard(()=>api.reload());
const templateRole=$("template-role"), templateLanguage=$("template-language");
templateRole.append(...Object.entries(categories).map(([key,label])=>option(key,label)));
let examples;
function showTemplate() {
    const example=examples?.[templateRole.value]?.[templateLanguage.value];
    $("template-preview").textContent=example ? "Subject: "+example[0]+"\n\n"+example[1] : "Loading templates…";
}
templateRole.onchange=showTemplate;
templateLanguage.onchange=showTemplate;
$("templates-open").onclick=guard(async()=>{
    const job=row(state.active);
    $("template-use").disabled=!eligible(job);
    if(job?.category) templateRole.value=job.category;
    $("templates").showModal();
    showTemplate();
    examples ||= await api.templateExamples();
    showTemplate();
});
$("template-use").onclick=guard(async()=>{
    const job=row(state.active);
    if(!eligible(job)) throw new Error("Select an email-ready job first.");
    const choice={template:templateRole.value,language:templateLanguage.value};
    await api.draft(job,choice);
    state.choices.set(job.id,choice);
    check(job,false);
    state.tab="draft";
    $("templates").close();
    render();
});
function options(settings){$("options-title").textContent=settings?"Settings":"More Filters";$("collection-options").hidden=!settings;$("filter-options").hidden=settings;$("options").showModal();}
function clearFilters() {
    $("last24").checked=false;
    for(const id of ["query","location","category","contract","status"]) $(id).value="";
    $("language").value="priority";
    state.view="discover";
    state.limit=35;
}
$("clear-filters").onclick=()=>{clearFilters();render();};
$("email-only").onclick=()=>{
    const active=$("status").value==="email";
    clearFilters();
    if(!active) {
        $("status").value="email";
        state.active=state.rows.find(job=>sample ? eligible(job) : job.batch_recipient)?.id;
        state.tab="draft";
    }
    render();
}; $("settings-open").onclick=()=>options(true);$("more-filters").onclick=()=>options(false);
$("sample-toggle").textContent=sample?"Open live dashboard":"Open sample dashboard";
$("sample-toggle").onclick=()=>{location.href=sample?"/":"/?sample=1";};
$("options-form").onsubmit=event=>{event.preventDefault();$("options").close();render();};
$("confirm").onclose=()=>{
    $("password").value="";
    $("send-error").hidden=true;
};
$("send-form").onsubmit=guard(async event=>{
    event.preventDefault();
    const ids=confirmed.ids.filter(id=>confirmed.included.has(id));
    if(!ids.length) {toast("Select at least one job to send.");return;}
    $("send-confirm").disabled=true;
    $("send-error").hidden=true;
    const password=$("password").value;
    const sendLabel=$("send-confirm").textContent;
    $("send-confirm").textContent="Starting batch…";
    $("send-confirm").setAttribute("aria-busy","true");
    if(!sample) {
        submittingBatch=true;
        deliveryProgress={state:"submitting",total:ids.length,sent:0,processed:0};
        renderDelivery();
    }
    try {
        const manual=confirmed.manualId ? {[confirmed.manualId]:$("manual-recipient").value.trim()} :
            Object.fromEntries(ids.filter(id=>id in confirmed.recipients).map(id=>[id,confirmed.recipients[id]]));
        await api.send(ids,confirmed.revision,confirmed.choices,password,$("sender").value.trim(),manual,confirmed.versions,confirmed.localBatch);
        if(!sample) {
            delivering=true;
            deliveryProgress={state:"checking",total:ids.length,sent:0,processed:0};
            renderDelivery();
        }
        for(const id of ids) state.checked.delete(id);
        $("confirm").close();render();
    } catch(error) {
        $("send-error").textContent=error.message;
        $("send-error").hidden=false;
        if(!sample) {
            deliveryProgress={state:"stopped",total:ids.length,sent:0,processed:0,message:error.message};
            renderDelivery();
        }
    } finally {
        submittingBatch=false;
        $("send-confirm").disabled=false;
        $("send-confirm").textContent=sendLabel;
        $("send-confirm").removeAttribute("aria-busy");
    }
});
$("automatic").disabled=sample;
$("activity").textContent=sample?"Sample data ready":"Connecting to JobFlow…";
render();


if (!sample) {
    const token=document.querySelector('meta[name="jobflow-token"]').content;
    async function request(path,data) {
        const headers={"X-JobBot-Token":token};
        const options={headers,cache:"no-store"};
        if(data!==undefined) {
            headers["Content-Type"]="application/json";
            Object.assign(options,{method:"POST",body:JSON.stringify(data)});
        }
        let response;
        try { response=await fetch(path,options); }
        catch { throw new Error("JobFlow is disconnected. Reopen the launcher and keep it running."); }
        if(response.status===403 && path.startsWith("/api/state")) {
            location.reload();
            throw new Error("Reconnecting to JobFlow…");
        }
        const result=await response.json();
        if(!response.ok) throw new Error(result.error || "JobFlow could not complete this action.");
        return result;
    }
    const listing=(job,choice)=>request("/api/listing/"+encodeURIComponent(job.id)+(choice?"?"+new URLSearchParams(choice):""));
    Object.assign(api,{
        collect:async()=>{
            const settings={query:$("query").value,limit:$("limit").value,pages:$("pages").value,
                sources:[...document.querySelectorAll("#sources input:checked")].map(input=>input.value)};
            try {
                await request("/api/jobs/start",settings);
            } catch(error) {
                if(error.message==="This action is unavailable.") {
                    await request("/api/collect",settings);
                } else if(error.message.startsWith("JobFlow is disconnected")) {
                    const status=await request("/api/state").catch(()=>null);
                    if(status?.mode==="collection") return;
                    throw new Error(status
                        ? "The launcher is running, but this browser request failed. Press Enter in the JobFlow terminal to collect jobs."
                        : "The browser cannot reach JobFlow. Press Enter in the launcher terminal to start collection there.");
                } else {
                    throw error;
                }
            }
        },
        infinity:async()=>{
            const state=await request("/api/state");
            if(!state.swarm_supported) throw new Error("Close the older JobFlow terminal and reopen the launcher to enable Scrape Jobs.");
            await request("/api/jobs/swarm",{query:$("query").value,limit:$("limit").value,pages:$("pages").value,
            sources:[...document.querySelectorAll("#sources input:checked")].map(input=>input.value)});
        },
        stop:()=>request("/api/stop",{}),
        profile:()=>request("/api/profile",{}),
        saveGmail:(sender,password)=>request("/api/gmail/save",{sender,password}),
        forgetGmail:()=>request("/api/gmail/forget",{}),
        templateExamples:()=>request("/api/templates"),
        cvs:()=>request("/api/cvs"),
        openCv:async query=>{
            const tab=window.open("about:blank","_blank");
            if(!tab) throw new Error("Allow a new tab to open the local CV.");
            tab.opener=null;
            try {
                const response=await fetch("/api/cv?"+new URLSearchParams(query),{headers:{"X-JobBot-Token":token}});
                if(!response.ok) throw new Error("The selected CV could not be opened.");
                const url=URL.createObjectURL(await response.blob());
                tab.location.replace(url);
                setTimeout(()=>URL.revokeObjectURL(url),60000);
            } catch(error) {tab.close();throw error;}
        },
        reload:async()=>{await request("/api/reload",{});toast("Profile reloaded.");},
        automatic:enabled=>request("/api/automatic",{enabled}),
        bookmark:(ids,saved)=>request("/api/bookmark",{ids,saved}),
        detail:job=>listing(job),
        draft:async(job,choice)=>{
            const result=await listing(job,choice);
            if(result.draft_error || !result.subject) throw new Error(result.draft_error || "This draft is no longer eligible.");
            return result;
        },
        markApplied:id=>request("/api/mark-applied",{id}),
        send:(ids,revision,choices,password,sender,manual,versions,local_batch)=>request("/api/send",{ids,revision,choices,password,sender,manual,versions,local_batch})
    });
    $("automatic").onchange=guard(()=>api.automatic($("automatic").checked));
    async function watch() {
        try {
            const result=await request("/api/state?revision="+state.revision);
            const previousMode=state.mode;
            state.mode=result.mode;
            gmailSaved=Boolean(result.gmail_saved);
            gmailSender=result.sender || "";
            generalTemplate=Boolean(result.general_template);
            infinity=result.infinity;
            delivering=result.delivery_active;
            if(!submittingBatch) deliveryProgress=result.delivery_progress;
            sendDelay=result.send_delay || sendDelay;
            renderDelivery();
            state.completed=result.completed;
            if(!$("sender").value && result.sender && !$("confirm").open) $("sender").value=result.sender;
            $("automatic").checked=result.automatic;
            $("mode").textContent=state.mode==="collection"?"Collecting jobs · "+result.added:
                state.mode==="delivery"?"Processing applications":infinity?"Continuous scraping":"Last collection";
            $("activity").textContent=result.message;
            const sources=result.sources || [];
            $("worker-status").hidden=!sources.length;
            $("worker-summary").textContent=sources.filter(source=>source.state==="Collecting").length+" workers active · "+sources.length+" sources";
            $("source-progress").replaceChildren(...(result.sources || []).map(source=>node("li",source.label+" · "+source.state+" · "+source.saved+" saved"+(source.message?" — "+source.message:""))));
            $("events").replaceChildren(...result.activity.map(message=>node("li",message)));
            if(result.rows && result.revision>=state.revision) {
                const previous=row(state.active);
                for(const id of state.checked) {
                    if(JSON.stringify(row(id))!==JSON.stringify(result.rows.find(job=>job.id===id))) state.checked.delete(id);
                }
                state.rows=result.rows;
                state.saved=new Set(result.saved);
                state.revision=result.revision;
                render(JSON.stringify(previous)===JSON.stringify(row(state.active)));
            } else if(previousMode!==state.mode && !state.rows.length) render();
            updateStats();
        } catch(error) { $("activity").textContent=error.message; }
        setTimeout(watch,1100);
    }
    watch();
}
