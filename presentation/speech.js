const d=require("docx");
const {Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,BorderStyle}=d;
const fs=require("fs");

const H=(t)=>new Paragraph({heading:HeadingLevel.HEADING_1,spacing:{before:360,after:120},
  children:[new TextRun({text:t,color:"12232E",font:"Cambria"})]});
const Slide=(n,t)=>new Paragraph({spacing:{before:400,after:80},
  border:{bottom:{style:BorderStyle.SINGLE,size:6,color:"E08A2B"}},
  children:[new TextRun({text:`SLIDE ${n}  ·  ${t}`,bold:true,size:24,
    color:"E08A2B",font:"Calibri"})]});
const Say=(t)=>new Paragraph({spacing:{after:160},indent:{left:200},
  children:[new TextRun({text:t,size:26,font:"Calibri",color:"1B2B36"})]});
const Note=(t)=>new Paragraph({spacing:{after:200},indent:{left:200},
  children:[new TextRun({text:t,size:20,italics:true,font:"Calibri",color:"5E7181"})]});

const doc=new Document({
  styles:{default:{document:{run:{font:"Calibri",size:24}}}},
  sections:[{properties:{page:{size:{width:12240,height:15840},
    margin:{top:1080,bottom:1080,left:1080,right:1080}}},
  children:[

  new Paragraph({spacing:{after:80},children:[new TextRun({text:"What I say on each slide",
    bold:true,size:40,font:"Cambria",color:"12232E"})]}),
  new Paragraph({spacing:{after:360},children:[new TextRun({
    text:"Summer progress update · about 6 minutes · talk normally, do not read this word for word",
    size:22,italics:true,color:"5E7181"})]}),

  Slide(1,"Title"),
  Say("Hey — so, quick update on where my thesis is."),
  Say("Basically over the break I decided to stop reading papers about this and just build the whole thing myself and run it. Like, actually run the experiments and see what happens. And honestly the whole point was to find out where it breaks in real life. It broke in a few places I did not expect, and that is the interesting part."),
  Say("The topic is silent failure. That is when the agent gives you an answer, it sounds confident, it looks completely normal — and it is just wrong. And nothing anywhere tells you."),
  Note("Pause here. Let that land before moving on."),

  Slide(2,"What I actually ran"),
  Say("So this is the scale of it. Three hundred and two benchmark runs, about twenty four thousand individual agent decisions, four different models. Whole thing cost me five dollars in API credits."),
  Say("What I do is I break the data pipeline on purpose. Four ways — I make the data old, I make it slow, I change the schema underneath the agent, or I strip out the meaning so the field names stop making sense. Then I measure what the agent does."),
  Say("And I also built two small tools out of it. One scores your pipeline before you put an agent on it. The other one sits in front and blocks bad data before the agent ever sees it."),
  Note("Do not linger. This slide is just scale — thirty seconds, then move."),

  Slide(3,"0.501 — the agent cannot tell"),
  Say("Okay, this is the number I would keep if you forget everything else."),
  Say("Zero point five zero one. A coin flip is zero point five."),
  Say("So what this measures is — when the agent tells you how confident it is, how well does that predict whether it is about to be confidently wrong? And the answer is, it does not. At all. It is noise."),
  Say("Which basically means you cannot ask the model to check itself. It does not know. So whatever safety you want, it has to come from outside the model."),
  Note("This is your strongest slide. Slow down, say the number clearly, and give them a second."),

  Slide(4,"Stale data moves the answer"),
  Say("This one changed how I think about the whole problem."),
  Say("Everyone assumes old data makes the agent worse at reasoning. Like it gets confused. I separated those two things and measured them apart — did the agent actually get worse, or did the correct answer just change while it was reading?"),
  Say("And it is almost entirely the second one. The agent reasons completely fine on stale data. It just answers the question the way it was five seconds ago."),
  Say("I got the same result three different ways, so I am fairly confident. And it kind of implies that when people report staleness hurting agent accuracy, some of that might be an artifact of how they measured it, not a real effect."),
  Note("Say the last sentence calmly. It is a strong claim — do not oversell it, just state it."),

  Slide(5,"Metadata does not help"),
  Say("So my next thought was obvious — just tell the agent the data is old. Give it the timestamp, it will be careful."),
  Say("I ran that. Every record carried its own age right next to the value. The agent could literally see the data was five seconds stale."),
  Say("Nothing changed. It did not hesitate more, it did not refuse more. Nothing."),
  Say("This surprised me honestly. But it makes sense when you think about it — an age is meaningless unless you have a rule to compare it against, and the model does not have a rule. So the rule has to live outside the model. Which is what I built next."),

  Slide(6,"The gate, and what it costs"),
  Say("So I built the thing that enforces it. It checks the data quality and refuses the batch before the agent is even asked."),
  Say("It works. But then I measured what it costs, and that is the part I did not expect."),
  Say("Two things. First — even on a completely healthy pipeline, no faults at all, the agent is still confidently wrong about fourteen percent of the time. Overall it is about twenty. So roughly three quarters of the problem is just the model, and no data tool can fix that part."),
  Say("Second — every blocking rule that actually helps also throws away good answers. Somewhere between seven and twenty one correct answers for every silent failure you stop."),
  Say("So it is a trade, not a free win. In something like medicine, obviously worth it. For a shopping assistant, probably not. But at least now it is a number instead of a guess."),

  Slide(7,"What did not satisfy me"),
  Say("Okay, now the honest part. I would rather tell you the weak spots myself than have someone find them in the defence."),
  Say("First — my agent is one API call. My title says agentic. One call is not really an agent. Nothing loops, nothing plans, nothing calls a tool twice. That bothers me."),
  Say("Second — I inject all the faults myself. It is clean science but I have never run this against a pipeline that broke on its own."),
  Say("Third — one of my experiments was almost circular. The latency fault cannot physically change what the agent reads, so getting no effect was guaranteed before I started. I am demoting that from a finding to just a design note."),
  Say("And fourth, the big one — I have results but I do not have a thesis. Chapter three is drafted. One, two, four and five are not written. That is genuinely the real gap right now."),
  Note("Do not rush this slide. Advisors trust you more after this, not less."),

  Slide(8,"What I want from the internship"),
  Say("So here is what I would actually want out of the internship."),
  Say("Number one, and this is the big one — access to a real pipeline. Real telemetry, where data goes stale and schemas drift on their own, without me causing it. Because then I can finally check whether my synthetic faults look anything like the real ones."),
  Say("Number two — build a proper multi-step agent. Retrieve, reason, act, retrieve again. And measure whether a small fault at step one gets bigger by step four. That is the honest version of agentic, and right now I do not have it."),
  Say("Number three — take the gate I built and run it in shadow mode on something live. It costs nothing, it needs no model call. Just let it watch a real pipeline and tell us what it would have blocked."),
  Say("And honestly the first one decides the other two. If I can get real data, the plan looks one way. If not, it looks completely different."),

  Slide(9,"What I need advice on"),
  Say("So that is where I am. Three things I would really like your read on."),
  Say("One — should I spend the autumn widening the experiments, or should I stop and write the thesis first? I have a feeling I know the answer but I want to hear it from you."),
  Say("Two — is real pipeline telemetry realistic through the internship, or should I plan around not having it?"),
  Say("And three — is the scope right? Am I trying to do too much here for one master's thesis?"),
  Say("That is it from me. Happy to go deeper on any part of it."),

  H("If they ask something hard"),
  new Paragraph({spacing:{after:120},children:[new TextRun({text:"“Why does this matter?”",bold:true})]}),
  Say("Because everyone's answer to bad data is “the model will notice”. I tested that. It does not notice."),
  new Paragraph({spacing:{after:120},children:[new TextRun({text:"“Your faults are synthetic, so is this realistic?”",bold:true})]}),
  Say("Agree first, do not defend. “Yeah, that is my main limitation, and it is exactly the thing I am hoping the internship fixes.” Turning it into your ask is stronger than arguing."),
  new Paragraph({spacing:{after:120},children:[new TextRun({text:"“Is one LLM call really an agent?”",bold:true})]}),
  Say("Fair. The pipeline is what I am studying, the agent is the measuring instrument — I held it constant on purpose. But yes, multi-step is the next step and I know it."),
  new Paragraph({spacing:{after:120},children:[new TextRun({text:"If the call runs short",bold:true})]}),
  Say("Just get slide three across. Zero point five zero one. If they remember one thing, that is the one."),
  ]}]});

Packer.toBuffer(doc).then(b=>{fs.writeFileSync("speech-notes.docx",b);console.log("written");});
