const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";                       // 13.3 x 7.5
const DARK="12232E", PAPER="FFFFFF", INK="1B2B36", MUTE="5E7181",
      AMBER="E08A2B", TEAL="2E8B95", SOFT="EDF3F5";
const H="Cambria", B="Calibri";

const titleOn=(s,t,col)=>s.addText(t,{x:0.7,y:0.5,w:11.9,h:1.0,fontSize:38,bold:true,
  fontFace:H,color:col||INK,valign:"middle"});

// 1 — title
let s=p.addSlide(); s.background={color:DARK};
s.addText("Silent Failure in Agentic AI Systems",{x:0.9,y:2.1,w:11.5,h:1.1,fontSize:44,
  bold:true,fontFace:H,color:PAPER});
s.addText("What happens to an AI agent when the data pipeline underneath it breaks",
  {x:0.9,y:3.25,w:10.5,h:0.6,fontSize:18,fontFace:B,color:"AAC0CC"});
s.addText("Summer break · self-directed build and experiments",
  {x:0.9,y:4.4,w:10.5,h:0.4,fontSize:14,fontFace:B,color:AMBER,bold:true});
s.addText("Shamsiddin Khamidov  ·  IT Park University",
  {x:0.9,y:6.3,w:10.5,h:0.4,fontSize:13,fontFace:B,color:"7E97A5"});

// 2 — what I ran
s=p.addSlide(); titleOn(s,"What I actually ran over the break");
const stats=[["302","benchmark runs"],["24,270","agent decisions"],["4","models tested"],
             ["$5.15","total API spend"],["350","tests, all green"]];
stats.forEach((d,i)=>{
  const x=0.7+i*2.44;
  s.addShape(p.ShapeType.roundRect,{x,y:1.9,w:2.2,h:1.5,fill:{color:SOFT},
    rectRadius:0.08,line:{color:SOFT}});
  s.addText(d[0],{x,y:2.05,w:2.2,h:0.7,fontSize:30,bold:true,fontFace:B,
    color:TEAL,align:"center",margin:0});
  s.addText(d[1],{x,y:2.72,w:2.2,h:0.5,fontSize:11,fontFace:B,color:MUTE,
    align:"center",margin:0});
});
s.addText([
 {text:"Four fault types injected into the data pipeline",options:{bullet:true,breakLine:true}},
 {text:"Stale data · slow delivery · schema drift · missing meaning",options:{bullet:true,breakLine:true}},
 {text:"Two tasks, two pipeline architectures, four different models",options:{bullet:true,breakLine:true}},
 {text:"Plus two working tools: one scores a pipeline, one blocks bad data",options:{bullet:true}},
],{x:0.85,y:3.9,w:11.3,h:2.6,fontSize:16,fontFace:B,color:INK,paraSpaceAfter:10});

// 3 — the headline number
s=p.addSlide(); s.background={color:DARK};
s.addText("0.501",{x:0.9,y:1.5,w:5.6,h:2.4,fontSize:130,bold:true,fontFace:B,
  color:AMBER,align:"center",valign:"middle",margin:0});
s.addText("A coin flip is 0.500",{x:0.9,y:3.9,w:5.6,h:0.5,fontSize:17,fontFace:B,
  color:"AAC0CC",align:"center",italic:true,margin:0});
s.addText("The agent cannot tell when it is wrong",{x:7.0,y:1.6,w:5.5,h:1.4,
  fontSize:31,bold:true,fontFace:H,color:PAPER});
s.addText([
 {text:"This is how well the agent's own confidence score predicts its own confidently-wrong answers.",options:{breakLine:true}},
 {text:"It carries no information at all.",options:{bold:true,breakLine:true}},
 {text:"So you cannot ask the model to check itself. Something outside it has to.",options:{}},
],{x:7.0,y:3.1,w:5.5,h:2.8,fontSize:16,fontFace:B,color:"D3E1E8",paraSpaceAfter:12});

// 4 — flip partition
s=p.addSlide(); titleOn(s,"Stale data does not confuse the agent");
s.addText("It moves the correct answer while the agent is reading",
  {x:0.7,y:1.4,w:11.9,h:0.5,fontSize:19,fontFace:B,color:MUTE,italic:true});
const cols=[["What everyone assumes","Old data makes the agent reason worse. It gets confused, makes mistakes, quality drops.","BFC9D0",INK],
            ["What I measured","The agent reasons perfectly fine. It just answers the question as it was five seconds ago.",TEAL,PAPER]];
cols.forEach((c,i)=>{
  const x=0.7+i*6.1;
  s.addShape(p.ShapeType.roundRect,{x,y:2.2,w:5.6,h:2.9,fill:{color:c[2]},
    rectRadius:0.08,line:{color:c[2]}});
  s.addText(c[0],{x:x+0.35,y:2.45,w:4.9,h:0.5,fontSize:19,bold:true,fontFace:H,
    color:c[3],margin:0});
  s.addText(c[1],{x:x+0.35,y:3.05,w:4.9,h:1.8,fontSize:16,fontFace:B,color:c[3],margin:0});
});
s.addText("Confirmed three independent ways. It means work that reports "+
  "“staleness degrades agents by X%” may be measuring an artifact, not an effect.",
  {x:0.7,y:5.5,w:11.9,h:0.9,fontSize:16,fontFace:B,color:INK,bold:true});

// 5 — detectability null
s=p.addSlide(); titleOn(s,"Telling the agent the data is old changes nothing");
s.addText([
 {text:"I ran an experiment where every record carried its own age, right next to the value.",options:{breakLine:true}},
 {text:"The agent could see the data was five seconds stale.",options:{breakLine:true}},
],{x:0.75,y:1.6,w:11.5,h:1.1,fontSize:18,fontFace:B,color:INK,paraSpaceAfter:8});
s.addShape(p.ShapeType.roundRect,{x:0.7,y:3.0,w:11.9,h:1.5,fill:{color:SOFT},
  rectRadius:0.08,line:{color:SOFT}});
s.addText("It did not become more cautious. Not even slightly.",
  {x:1.1,y:3.25,w:11.1,h:1.0,fontSize:26,bold:true,fontFace:H,color:AMBER,valign:"middle",margin:0});
s.addText([
 {text:"This one genuinely surprised me — I assumed metadata would make it careful.",options:{bullet:true,breakLine:true}},
 {text:"An age means nothing without a rule to judge it against, and the model has no rule.",options:{bullet:true,breakLine:true}},
 {text:"So the rule has to live outside the model. That is what I built next.",options:{bullet:true}},
],{x:0.85,y:4.9,w:11.3,h:1.9,fontSize:16,fontFace:B,color:INK,paraSpaceAfter:10});

// 6 — the gate, priced
s=p.addSlide(); titleOn(s,"I built the enforcer — then put a price on it");
s.addChart(p.ChartType.bar,[{name:"Silent failure rate",labels:["Healthy pipeline","All pipelines"],
  values:[14.2,19.6]}],{x:0.7,y:1.7,w:6.0,h:3.4,barDir:"col",chartColors:[TEAL,AMBER],
  showTitle:true,title:"Where silent failure comes from (%)",titleFontSize:14,
  titleColor:INK,titleFontFace:B,showValue:true,dataLabelPosition:"outEnd",
  dataLabelFontSize:14,dataLabelColor:INK,showLegend:false,
  catAxisLabelColor:MUTE,valAxisLabelColor:MUTE,catAxisLabelFontSize:12,
  valAxisLabelFontSize:11,valGridLine:{color:"E3EAEE",size:1},
  catGridLine:{style:"none"},valAxisMaxVal:25});
s.addText([
 {text:"Three quarters of the problem is the model, not the data.",options:{bold:true,breakLine:true}},
 {text:"Even on a perfect pipeline the agent is still confidently wrong 14% of the time. No data-quality tool can touch that part.",options:{breakLine:true}},
],{x:7.1,y:1.8,w:5.5,h:2.0,fontSize:16,fontFace:B,color:INK,paraSpaceAfter:10});
s.addShape(p.ShapeType.roundRect,{x:7.1,y:3.9,w:5.5,h:1.9,fill:{color:DARK},
  rectRadius:0.08,line:{color:DARK}});
s.addText("7 to 21",{x:7.35,y:4.05,w:5.0,h:0.8,fontSize:38,bold:true,fontFace:B,
  color:AMBER,margin:0});
s.addText("correct answers thrown away for every silent failure you prevent",
  {x:7.35,y:4.85,w:5.0,h:0.8,fontSize:14,fontFace:B,color:"C3D4DC",margin:0});
s.addText("Blocking bad data works — but it is a trade, not a free win. "+
  "Worth it in medicine. Probably not for a shopping assistant.",
  {x:0.7,y:5.9,w:11.9,h:0.8,fontSize:16,fontFace:B,color:INK,italic:true});

// 7 — limitations
s=p.addSlide(); titleOn(s,"What did not satisfy me");
const lims=[["My agent is one API call","The title says “agentic”. One call is not an agent — nothing loops, plans, or calls a tool twice."],
 ["The faults are synthetic","I inject them myself. Clean science, but I have never run this against a pipeline that broke on its own."],
 ["One experiment was near-circular","The latency fault cannot change what the agent reads, so “no effect” was guaranteed. Demoting it to a design note."],
 ["I have results, not a thesis","Chapter 3 is drafted. Chapters 1, 2, 4 and 5 are not. That is the real gap."]];
lims.forEach((l,i)=>{
  const y=1.55+i*1.28;
  s.addShape(p.ShapeType.ellipse,{x:0.75,y:y+0.12,w:0.42,h:0.42,fill:{color:AMBER},
    line:{color:AMBER}});
  s.addText(String(i+1),{x:0.75,y:y+0.12,w:0.42,h:0.42,fontSize:15,bold:true,
    fontFace:B,color:PAPER,align:"center",valign:"middle",margin:0});
  s.addText(l[0],{x:1.4,y:y,w:11.0,h:0.42,fontSize:18,bold:true,fontFace:H,
    color:INK,margin:0});
  s.addText(l[1],{x:1.4,y:y+0.44,w:11.0,h:0.68,fontSize:14,fontFace:B,color:MUTE,margin:0});
});

// 8 — internship
s=p.addSlide(); titleOn(s,"What I want from the internship");
const asks=[["A real pipeline","Production telemetry, where staleness and schema drift happen on their own — so I can check whether my synthetic faults resemble genuine ones at all."],
 ["Multi-step agents","Move from one call to retrieve → reason → act → retrieve again, and measure whether a small fault compounds across steps. The honest version of “agentic”."],
 ["Run the gate for real","It works today, costs nothing, needs no model call. Put it in shadow mode on a live pipeline and see what it would have caught."]];
asks.forEach((a,i)=>{
  const x=0.7+i*4.07;
  s.addShape(p.ShapeType.roundRect,{x,y:1.75,w:3.75,h:3.9,fill:{color:SOFT},
    rectRadius:0.08,line:{color:SOFT}});
  s.addShape(p.ShapeType.ellipse,{x:x+0.35,y:2.05,w:0.5,h:0.5,fill:{color:TEAL},line:{color:TEAL}});
  s.addText(String(i+1),{x:x+0.35,y:2.05,w:0.5,h:0.5,fontSize:17,bold:true,fontFace:B,
    color:PAPER,align:"center",valign:"middle",margin:0});
  s.addText(a[0],{x:x+0.35,y:2.75,w:3.1,h:0.6,fontSize:20,bold:true,fontFace:H,color:INK,margin:0});
  s.addText(a[1],{x:x+0.35,y:3.45,w:3.1,h:2.0,fontSize:14,fontFace:B,color:MUTE,margin:0});
});
s.addText("The first one changes everything else — it decides which of the other two is worth planning around.",
  {x:0.7,y:5.9,w:11.9,h:0.6,fontSize:16,fontFace:B,color:INK,italic:true});

// 9 — the ask
s=p.addSlide(); s.background={color:DARK};
s.addText("Where I would like your advice",{x:0.9,y:1.6,w:11.5,h:0.9,fontSize:36,
  bold:true,fontFace:H,color:PAPER});
s.addText([
 {text:"Do I spend the autumn widening the experiments, or finish the write-up first?",options:{bullet:true,breakLine:true}},
 {text:"Can the internship realistically give me access to real pipeline telemetry?",options:{bullet:true,breakLine:true}},
 {text:"Is the scope right — or am I trying to do too much for one thesis?",options:{bullet:true}},
],{x:1.0,y:3.0,w:11.0,h:2.4,fontSize:20,fontFace:B,color:"D3E1E8",paraSpaceAfter:16});
s.addText("Thank you — happy to go deeper on any of it",{x:0.9,y:6.2,w:11.5,h:0.5,
  fontSize:15,fontFace:B,color:AMBER,bold:true});

p.writeFile({fileName:"summer-update.pptx"}).then(()=>console.log("written"));
