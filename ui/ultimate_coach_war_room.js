  // ---- Captain's War Room (embedded by ui/ultimate_coach.py inside the page script) ----
  // Mirrors analytics/ultimate_coach_war_room.py and the Excel War Room / Lineup Lab texts:
  // evidence category = the sign of a recorded direct record only (G/R/E), else I (shared
  // opponents only) or X (nothing). No thresholds, weights, odds or confidence. Planning marks
  // (availability / lineup / opponent played / notes) are the captain's inputs, kept per team
  // scope in this browser only, and never change any evidence.
  var WR_CAT_LABELS={G:"Favorable direct record",R:"Concerning direct record",E:"Even direct record",I:"Indirect evidence only",X:"Insufficient evidence"};
  var WR_SENDABLE={G:true,E:true,I:true};
  var WR_TZ=(DATA.match_day&&DATA.match_day.display_timezone)||"America/Denver";
  var WR_STATE={pair:null};
  // Set by Match Day when its current selection has no fixture to follow (no date, no match, bye,
  // opponent without a roster, several fixtures awaiting a choice, no team): {when, text}. The Tonight
  // panel then states that instead of going blank or keeping a previous fixture (GPT audit #84).
  var WR_TONIGHT_NOTE=null;
  function wrKnown(x){return x!==null&&x!==undefined;}
  function wrCategory(c){if(c.direct){var w=c.direct.w,l=c.direct.g-w;return w>l?"G":(w<l?"R":"E");}return c.shared?"I":"X";}
  function wrCell(c){
    if(c.direct) return wlText(c.direct.w,c.direct.g)+" ("+c.direct.g+")";
    if(c.shared) return "≈ "+wlText(c.ow,c.og)+" vs "+wlText(c.tw,c.tg)+" ("+c.shared+" shared)";
    return "No evidence";
  }
  function wrExplain(c){
    return [c.direct?"Direct: "+wlText(c.direct.w,c.direct.g)+" in "+plural(c.direct.g,"meeting"):"No direct meetings",
      c.shared?"Indirect: "+plural(c.shared,"shared opponent")+" — ours "+wlText(c.ow,c.og)+" ("+plural(c.og,"game")+"), theirs "+wlText(c.tw,c.tg)+" ("+plural(c.tg,"game")+")":"no shared opponents"].join(" · ");
  }
  var WR_CAT_WORD={G:"favorable",R:"concerning",E:"even"};
  // Why a player appears as a send (mirrors analytics.ultimate_coach_war_room.reason).
  function wrReason(c){
    if(c.direct) return wlText(c.direct.w,c.direct.g)+" direct record ("+plural(c.direct.g,"meeting")+") — "+WR_CAT_WORD[wrCategory(c)];
    if(c.shared) return "shared-opponent results only: ours "+wlText(c.ow,c.og)+" vs theirs "+wlText(c.tw,c.tg)+" across "+plural(c.shared,"shared opponent")+" (no direct meetings)";
    return "no recorded evidence";
  }
  // Calendar day in the disclosed display timezone for an offset-aware source timestamp
  // (same accept rule as analytics.ultimate_coach_match_day.parse_match_date: naive -> No data).
  var WR_DAY=(function(){try{return new Intl.DateTimeFormat("en-US",{timeZone:WR_TZ,year:"numeric",month:"2-digit",day:"2-digit"});}catch(e){return null;}})();
  var WR_AWARE=/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/;
  var WR_WD=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"],WR_MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function wrInstant(raw){var s=String(raw||"").trim();if(!WR_AWARE.test(s)) return null;s=s.replace(" ","T").replace(/([+-]\d{2})(\d{2})$/,"$1:$2");var t=Date.parse(s);return isFinite(t)?t:null;}
  function wrDayLabel(t){
    if(t===null||!WR_DAY) return "No data";
    var p={};WR_DAY.formatToParts(new Date(t)).forEach(function(x){p[x.type]=x.value;});
    var d=new Date(Date.UTC(+p.year,+p.month-1,+p.day));
    return WR_WD[d.getUTCDay()]+" "+WR_MON[+p.month-1]+" "+(+p.day)+", "+p.year;
  }
  function wrCmpTime(a,b){if(a===b) return 0;if(a===null) return -1;if(b===null) return 1;return a<b?-1:1;}
  function wrBuckets(pid,fmt){
    var b={};
    rowsFor(pid,fmt).forEach(function(r){var sl=val(r,"opponent_skill_level");var ok=typeof sl==="number"&&sl>0;var k=ok?String(sl):"";var e=b[k]||(b[k]={sl:ok?sl:null,w:0,g:0});e.g+=1;if(val(r,"result")==="W") e.w+=1;});
    var known=Object.keys(b).filter(function(k){return k!=="";}).map(function(k){return b[k];}).sort(function(x,y){return x.sl-y.sl;});
    if(!known.length) return ["No opponent skill levels recorded","—","—"];
    function lab(e){return "SL"+Math.trunc(e.sl)+" ("+wlText(e.w,e.g)+")";}
    return [known.map(function(e){return "vs SL"+Math.trunc(e.sl)+" "+wlText(e.w,e.g);}).join(" · "),
      known.filter(function(e){return e.w>e.g-e.w;}).map(lab).join(", ")||"None recorded",
      known.filter(function(e){return e.w<e.g-e.w;}).map(lab).join(", ")||"None recorded"];
  }
  // Complete scopes only (mirrors _career_text): unknown wins never become losses.
  function wrCareer(p,fmt){
    var rows=((p&&p.career_stats)||[]).filter(function(r){return r.format===fmt;});
    if(!rows.length) return "No career stats captured";
    var c=careerComplete(rows),gap=c.incomplete?plural(c.incomplete,"league scope")+" with missing wins or games not counted":"";
    if(!c.g) return c.incomplete?"No complete career record captured ("+gap+")":"No career games recorded";
    return wlText(c.w,c.g)+" (league-scoped lifetime "+fmtLabel(fmt)+(gap?"; "+gap+")":")");
  }
  function warRoomPair(ta,tb,fmt){
    var ours=ta.players.slice().sort(memberOrder),theirs=tb.players.slice().sort(memberOrder);
    var blocks=theirs.map(function(opp){return rankVsOpponent(ours,opp,fmt);});
    blocks.forEach(function(b){b.byMember={};b.rows.forEach(function(r,i){r.category=wrCategory(r.c);r.cell=wrCell(r.c);r.explanation=wrExplain(r.c);r.reason=wrReason(r.c);r.position=i+1;b.byMember[String(r.member.id)]=r;});});
    var matrix=ours.map(function(m){return {member:m,cells:blocks.map(function(b){return b.byMember[String(m.id)];})};});
    var concerning=[];
    blocks.forEach(function(b,j){b.rows.forEach(function(r){if(r.category!=="R") return;var w=r.c.direct.w,g=r.c.direct.g;
      concerning.push({our:r.member,opp:b.opponent,j:j,w:w,g:g,text:r.player+" vs "+b.opponent_label+": "+wlText(w,g)+" direct ("+plural(g,"meeting")+")"});});});
    concerning.sort(function(x,y){var a=x.g-2*x.w,b=y.g-2*y.w;if(a!==b) return b-a;if(x.g!==y.g) return y.g-x.g;var mo=memberOrder(x.our,y.our);return mo!==0?mo:x.j-y.j;});
    var cards=blocks.map(function(b,j){
      var opp=b.opponent;
      var met=b.rows.filter(function(r){return !!r.c.direct;}).sort(function(x,y){return memberOrder(x.member,y.member);});
      var tw=0,tg=0;met.forEach(function(r){tw+=r.c.direct.g-r.c.direct.w;tg+=r.c.direct.g;});
      var sharedN=b.rows.filter(function(r){return !!r.c.shared;}).length,bk=wrBuckets(opp.id,fmt),missing=[];
      if(!wrKnown(opp.skill_level)) missing.push("No captured SL on this team's roster");
      if(b.opponent_games===0) missing.push("No recorded "+fmtLabel(fmt)+" games in the verified evidence");
      if(!tg) missing.push("No meetings with our roster");
      var session=tb.session_name||"";
      return {j:j,opponent:opp,label:b.opponent_label,sl:wrKnown(opp.skill_level)?String(opp.skill_level):"No data",
        team_record:(!wrKnown(opp.matches_won)||!wrKnown(opp.matches_played))?"No data":wlText(opp.matches_won,opp.matches_played)+" (this team"+(session?", "+session+")":")"),
        lifetime:wrCareer(PLAYERS[String(opp.id)],fmt),sample:b.opponent_sample,
        vs_ours:tg?wlText(tw,tg)+" in "+plural(tg,"meeting")+" with "+met.length+" of our "+ours.length+" players":"No recorded meetings with our roster — unknown, not a sign of weakness",
        met_list:tg?met.map(function(r){return "vs "+r.player+": "+wlText(r.c.direct.g-r.c.direct.w,r.c.direct.g);}).join(" · "):"—",
        their_wins:tw,their_games:tg,players_met:met.length,
        shared_summary:sharedN?"Shared opponents with "+sharedN+" of our "+ours.length+" players":"No shared opponents with our roster",
        by_sl:bk[0],winning_sl:bk[1],losing_sl:bk[2],missing:missing.join("; ")||"None noted"};
    });
    var threats=cards.filter(function(c){return c.their_games&&c.their_wins>c.their_games-c.their_wins;});
    threats.sort(function(x,y){var a=2*x.their_wins-x.their_games,b=2*y.their_wins-y.their_games;if(a!==b) return b-a;
      if(x.their_wins!==y.their_wins) return y.their_wins-x.their_wins;if(x.their_games!==y.their_games) return y.their_games-x.their_games;return memberOrder(x.opponent,y.opponent);});
    threats.forEach(function(c){c.threat_text=c.label+" · SL "+c.sl+" · "+wlText(c.their_wins,c.their_games)+" vs our roster ("+plural(c.their_games,"meeting")+", "+c.players_met+" of our players)";});
    var meetings=[];
    ours.forEach(function(m){theirs.forEach(function(o){
      var games=rowsFor(m.id,fmt).filter(function(r){return String(val(r,"opponent_id"))===String(o.id);}).map(function(r){
        var t=wrInstant(val(r,"match_date"));
        return {t:t,date:wrDayLabel(t),session:val(r,"session_name")||"No data",result:val(r,"result")||"No data",
          own_sl:val(r,"own_skill_level"),opp_sl:val(r,"opponent_skill_level"),points:val(r,"points_earned"),our:m,opp:o};
      });
      games.sort(function(x,y){return wrCmpTime(y.t,x.t);});
      meetings=meetings.concat(games);
    });});
    meetings.sort(function(x,y){var c=wrCmpTime(y.t,x.t);return c!==0?c:memberOrder(y.our,x.our);});
    return {format:fmt,ours:ours,theirs:theirs,blocks:blocks,matrix:matrix,concerning:concerning,cards:cards,threats:threats,meetings:meetings};
  }
  window.__ucCareerText=wrCareer;
  window.__ucWarRoomPair=function(ourKey,oppKey,fmt){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt);
    return {matrix:w.matrix.map(function(r){return r.cells.map(function(c){return [c.category,c.cell,c.explanation,c.reason];});}),
      best:w.blocks.map(function(b){return b.rows.filter(function(r){return WR_SENDABLE[r.category];}).map(function(r){return r.player;});}),
      concerning:w.concerning.map(function(c){return c.text;}),threats:w.threats.map(function(c){return c.threat_text;}),
      cards:w.cards.map(function(c){return [c.sl,c.team_record,c.lifetime,c.sample,c.vs_ours,c.met_list,c.shared_summary,c.by_sl,c.winning_sl,c.losing_sl,c.missing];}),
      meetings:w.meetings.map(function(g){return [g.date,g.our.id,g.opp.id,g.result,g.session];})};
  };

  // ---- planning marks: per FIXTURE (our team + opponent + fixture id), this browser only, never evidence ----
  // Availability / Planned / Played describe one match night, so they are keyed by the exact fixture
  // (GPT audit #84: team-only keys leaked "Played" into the next fixture). Teams picked by hand, with no
  // Match Day fixture, use their own "manual" context. Coach notes describe a player, so they are kept
  // separately per opponent team + player and follow that player to every fixture. v1 (team-keyed) marks
  // are deliberately not migrated: they cannot be attributed to a fixture.
  // Coach notes (tags + observation) describe a PLAYER: kept per player id in plan.coach and shown on every
  // fixture's card. Notes written by the earlier per-team version (plan.notes[team][player].n) are carried over.
  var WR_PLAN=(function(){
    var o=null;try{o=JSON.parse(window.localStorage.getItem("ultimate-coach:plan-v2")||"null");}catch(e){o=null;}
    var p=(o&&typeof o==="object")?{our:o.our||{},opp:o.opp||{},notes:o.notes||{},cap:o.cap||{},coach:o.coach||{}}:{our:{},opp:{},notes:{},cap:{},coach:{}};
    Object.keys(p.notes).forEach(function(scope){var s=p.notes[scope]||{};Object.keys(s).forEach(function(pid){
      var n=s[pid]&&s[pid].n;if(n&&!(p.coach[pid]&&p.coach[pid].n)){(p.coach[pid]||(p.coach[pid]={})).n=n;}});});
    // One-time migration (GPT audit #84): once imported, the legacy copy is removed and saved, so a note the
    // captain later clears is not resurrected on the next load.
    if(Object.keys(p.notes).length){p.notes={};p._migrated=true;}
    return p;
  })();
  if(WR_PLAN._migrated){delete WR_PLAN._migrated;wrSave();}
  var WR_COACH_TAGS=DATA.coach_tags||[];
  function wrCoach(pid){return WR_PLAN.coach[String(pid)]||{};}
  function wrCoachSummary(pid){
    var c=wrCoach(pid),t1=c.t1||"",t2=c.t2||"",n=String(c.n||"").trim();
    var s=(t1+(t1&&t2?" · ":"")+t2+((t1||t2)&&n?": ":"")+n).trim();
    return s?"Coach: "+s:"";
  }
  function wrSetCoach(pid,field,value){var c=WR_PLAN.coach[String(pid)]||(WR_PLAN.coach[String(pid)]={});if(value) c[field]=value; else delete c[field];wrSave();}
  function wrSave(){try{window.localStorage.setItem("ultimate-coach:plan-v2",JSON.stringify(WR_PLAN));}catch(e){}}
  function wrCtx(ta,tb){
    var c=MATCHUP_CONTEXT,fixture="manual";
    if(c&&tb&&c.ourKey===ta.key&&c.oppKey===tb.key&&c.fixture) fixture="fixture:"+String(c.fixture.match_id!==undefined&&c.fixture.match_id!==null?c.fixture.match_id:c.fixture.match_external_id);
    return ta.key+"||"+(tb?tb.key:"")+"||"+fixture;
  }
  function wrMark(kind,scope,pid){var s=WR_PLAN[kind][scope];return (s&&s[String(pid)])||{};}
  function wrSetMark(kind,scope,pid,field,value){var s=WR_PLAN[kind][scope]||(WR_PLAN[kind][scope]={});var m=s[String(pid)]||(s[String(pid)]={});if(value) m[field]=value; else delete m[field];wrSave();}
  function wrAvail(scope,pid){var a=wrMark("our",scope,pid).a;return a==="Available"||a==="Unavailable"?a:"Unknown";}
  function wrLineup(scope,pid){var l=wrMark("our",scope,pid).l;return l==="Planned"||l==="Played"?l:"";}
  function wrRemaining(scope,pid){return wrAvail(scope,pid)!=="Unavailable"&&wrLineup(scope,pid)!=="Played";}
  function wrPlayed(scope,pid){return !!wrMark("opp",scope,pid).p;}


  function wrPlan(w,ta,tb){
    var ck=wrCtx(ta,tb);
    var rem={};w.ours.forEach(function(m){rem[String(m.id)]=wrRemaining(ck,m.id);});
    var unplayed=w.theirs.map(function(o){return !wrPlayed(ck,o.id);});
    var sends=w.blocks.map(function(b){return b.rows.filter(function(r){return WR_SENDABLE[r.category]&&rem[String(r.member.id)];});});
    var green=w.blocks.map(function(b){return b.rows.filter(function(r){return r.category==="G"&&rem[String(r.member.id)];}).length;});
    var risks=[],unique=[];
    w.theirs.forEach(function(o,j){if(unplayed[j]&&green[j]===0) risks.push(w.blocks[j].opponent_label+" — "+(sends[j].length>0?"only even or indirect evidence left":"no evidence-backed option left"));});
    w.ours.forEach(function(m,i){
      if(!rem[String(m.id)]) return;
      var js=[];w.blocks.forEach(function(b,j){if(unplayed[j]&&green[j]===1&&w.matrix[i].cells[j].category==="G") js.push(j);});
      if(js.length) unique.push(playerRef(m)+" — only favorable direct option vs "+w.blocks[js[0]].opponent_label+(js.length>1?" (and "+(js.length-1)+" more)":""));
    });
    var remN=0,unk=0,remSL=0,remMiss=0,selN=0,selSL=0,selMiss=0;
    w.ours.forEach(function(m){
      var r=rem[String(m.id)],l=wrLineup(ck,m.id),sl=m.skill_level;
      if(r){remN++;if(wrAvail(ck,m.id)==="Unknown") unk++;if(wrKnown(sl)) remSL+=sl; else remMiss++;}
      if(l){selN++;if(wrKnown(sl)) selSL+=sl; else selMiss++;}
    });
    var cap=WR_PLAN.cap[ta.key],openN=unplayed.filter(Boolean).length;
    var greenOpps=0,sendOpps=0;w.theirs.forEach(function(o,j){if(!unplayed[j]) return;if(green[j]>0) greenOpps++;if(sends[j].length>0) sendOpps++;});
    var n=w.ours.length;
    return {ck:ck,rem:rem,unplayed:unplayed,sends:sends,risks:risks,unique:unique,
      threats:w.threats.filter(function(c){return unplayed[c.j];}).slice(0,3),
      concerning:w.concerning.filter(function(c){return rem[String(c.our.id)]&&unplayed[c.j];}).slice(0,5),
      metrics:[
        ["Remaining players",!n?"—":remN+" of "+n+(unk>0?" ("+unk+" with unknown availability — still counted as remaining)":"")],
        ["Remaining skill total",!n?"—":(remMiss===0?remSL+" (all remaining players have a captured SL)":remSL+" known subtotal · "+remMiss+" remaining player(s) without a captured SL — not a complete total")],
        ["Selected lineup (Planned + Played)",selN===0?"No players marked Planned or Played yet.":(selMiss===0?"Skill total "+selSL+" for "+selN+" selected player(s)":"Known subtotal "+selSL+" · "+selMiss+" selected player(s) without a captured SL")+(cap?" · your reference cap: "+cap+" (user-entered, not verified)":"")+" — not a lineup-legality check."],
        ["Roster flexibility",openN===0?"—":"Favorable direct option left vs "+greenOpps+" of "+openN+" unplayed opponents · any evidence-backed option vs "+sendOpps+" of "+openN]
      ]};
  }

  // ---- Next Send (mirrors analytics.ultimate_coach_war_room.next_send / next_send_lines) ----
  // Medals only for ORDERED direct candidates (favorable, then even) in ranking order; same evidence = same
  // medal, named as tied. Shared-opponent-only candidates are one unordered "≈" group; concerning records
  // are "Avoid" (worst first); no evidence is unknown, never weak. Nothing is re-scored or weighted.
  var WR_MEDALS=["🥇","🥈","🥉"];
  function wrNextSend(w,j,rem,unplayed){
    var b=w.blocks[j],rows=b.rows.filter(function(r){return rem[String(r.member.id)];});
    var onlyGreen={};
    w.blocks.forEach(function(o,k){if(k===j||!unplayed[k]) return;
      var g=o.rows.filter(function(r){return r.category==="G"&&rem[String(r.member.id)];});
      if(g.length===1){var id=String(g[0].member.id);(onlyGreen[id]||(onlyGreen[id]=[])).push(o.opponent.name);}});
    var groups=[];
    rows.forEach(function(r){if(r.category!=="G"&&r.category!=="E") return;var last=groups[groups.length-1];
      if(last&&String(last[0].rank).replace("=","")===String(r.rank).replace("=","")) last.push(r); else groups.push([r]);});
    var medals=[],more=0;
    groups.forEach(function(group,g){
      if(g>=WR_MEDALS.length){more+=group.length;return;}
      group.forEach(function(r){var save=onlyGreen[String(r.member.id)];
        medals.push({medal:WR_MEDALS[g],member:r.member,player:r.player,category:r.category,reason:r.reason,
          tied_with:group.filter(function(o){return o!==r;}).map(function(o){return o.member.name;}),
          save:save?"consider saving — our only favorable direct option vs "+save.join(", "):""});});
    });
    var pick=function(cat){return function(r){return r.category===cat;};},brief=function(r){return {member:r.member,player:r.player,reason:r.reason};};
    var unordered=rows.filter(pick("I")).map(brief),avoid=rows.slice().reverse().filter(pick("R")).map(brief);
    var unknown=rows.filter(pick("X")).map(function(r){return r.player;});
    var headline=!unplayed[j]?b.opponent.name+" has already played."
      :medals.length?"Best-supported response: "+medals[0].member.name+(medals[0].tied_with.length?" or "+medals[0].tied_with.join(", ")+" (tied)":"")
      :unordered.length?"No direct record to order — shared-opponent candidates only (≈, not ordered)"
      :"No evidence-backed option left among our remaining players";
    return {opponent:b.opponent,label:b.opponent_label,headline:headline,medals:medals,more:more,unordered:unordered,avoid:avoid,unknown:unknown};
  }
  function wrNextSendLines(ns){
    var lines=[ns.headline];
    ns.medals.forEach(function(m){lines.push(m.medal+" "+m.player+" — "+m.reason+(m.tied_with.length?" · tied with "+m.tied_with.join(", "):"")+(m.save?" · "+m.save:""));});
    if(ns.more) lines.push("+ "+plural(ns.more,"more direct candidate")+" below the top three");
    ns.unordered.forEach(function(u){lines.push("≈ "+u.player+" — "+u.reason);});
    ns.avoid.forEach(function(a){lines.push("⚠ Avoid "+a.player+" — "+a.reason);});
    if(ns.unknown.length) lines.push("❓ Unknown (no evidence, not weak): "+ns.unknown.join(", "));
    return lines;
  }
  window.__ucNextSend=function(ourKey,oppKey,fmt,j,remainingIds,unplayed){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt),rem={};
    w.ours.forEach(function(m){rem[String(m.id)]=!remainingIds||remainingIds.map(String).indexOf(String(m.id))>=0;});
    return wrNextSendLines(wrNextSend(w,j,rem,unplayed||w.theirs.map(function(){return true;})));
  };
  // The Next Send card: chips for every unplayed opponent (the one they put up), then the responses.
  function wrNextSendCard(w,plan){
    var open=w.theirs.map(function(o,j){return j;}).filter(function(j){return plan.unplayed[j];});
    if(!open.length) return '<div id="next-send" class="next-send"><h3>Who should I send next?</h3><p class="muted">Every opponent has played.</p></div>';
    var sel=open.filter(function(j){return String(w.theirs[j].id)===String(WR_STATE.next);})[0];
    if(sel===undefined) sel=open[0];
    var ns=wrNextSend(w,sel,plan.rem,plan.unplayed),opp=w.theirs[sel],note=wrCoachSummary(opp.id);
    var li=function(cls,html){return '<li class="'+cls+'">'+html+'</li>';};
    return '<div id="next-send" class="next-send"><h3>Who should I send next?</h3>'
      +'<div class="ns-chips" role="group" aria-label="Opponent they put up"><span class="ns-ask">They put up:</span>'
      +open.map(function(j){var o=w.theirs[j];return '<button type="button" class="ns-chip'+(j===sel?' on':'')+'" data-next="'+esc(o.id)+'" aria-pressed="'+(j===sel)+'">'+esc(o.name+" · SL "+slText(o))+'</button>';}).join("")+'</div>'
      +'<p class="ns-head"><b>'+esc(ns.headline)+'</b></p><ul class="ns-list">'
      +ns.medals.map(function(m){return li("ns-medal cat-border-"+m.category,'<span class="ns-m">'+m.medal+'</span> <b>'+esc(m.member.name)+'</b> — '+esc(m.reason)
        +(m.tied_with.length?' <span class="muted">· tied with '+esc(m.tied_with.join(", "))+'</span>':'')+(m.save?' <span class="ns-save">· '+esc(m.save)+'</span>':'')
        +' <button type="button" class="ns-send secondary" data-send-our="'+esc(m.member.id)+'" data-send-opp="'+esc(opp.id)+'" aria-label="Mark '+esc(m.member.name)+' sent vs '+esc(opp.name)+'">✓ Sent</button>');}).join("")
      +(ns.more?li("muted","+ "+esc(plural(ns.more,"more direct candidate"))+" below the top three (see Best sends)"):"")
      +ns.unordered.map(function(u){return li("ns-unordered",'≈ '+esc(u.member.name)+' — '+esc(u.reason)+' <span class="muted">(not ordered)</span>');}).join("")
      +ns.avoid.map(function(a){return li("ns-avoid",'⚠ Avoid <b>'+esc(a.member.name)+'</b> — '+esc(a.reason));}).join("")
      +(ns.unknown.length?li("ns-unknown",'❓ Unknown (no evidence, not weak): '+esc(ns.unknown.map(function(p){return p.replace(/ \(APA record ID [^)]*\)$/,"");}).join(", "))):"")
      +'</ul>'+(note?'<p class="ns-coach">📝 '+esc(note)+' <span class="muted">(your opinion, not APA facts)</span></p>':'')
      +'</div>';
  }

  function wrList(items,empty){return '<ul class="wr-list">'+(items.length?items.map(function(t){return '<li>'+esc(t)+'</li>';}).join(""):'<li class="muted">'+esc(empty)+'</li>')+'</ul>';}
  function wrChip(cat){return '<span class="cat-dot cat-'+cat+'" title="'+esc(WR_CAT_LABELS[cat])+'"></span>';}
  // "Tonight" at the top of the page: the fixture and the decision overview first, setup below.
  function wrTonight(w,plan,ta,tb){
    var el=document.getElementById("tonight");
    if(!el) return;
    if(!w){el.innerHTML="";return;}
    var c=MATCHUP_CONTEXT,ctx=c&&c.ourKey===ta.key&&c.oppKey===tb.key&&c.fixture?c:null,f=ctx?ctx.fixture:null;
    var remN=w.ours.filter(function(m){return plan.rem[String(m.id)];}).length;
    var av={Available:0,Unavailable:0,Unknown:0},used=0,planned=0;
    w.ours.forEach(function(m){av[wrAvail(plan.ck,m.id)]++;var l=wrLineup(plan.ck,m.id);if(l==="Played") used++;else if(l==="Planned") planned++;});
    var cat={G:0,R:0,E:0,I:0,X:0};w.matrix.forEach(function(row){row.cells.forEach(function(c){cat[c.category]++;});});
    var noSL=w.theirs.filter(function(o){return !wrKnown(o.skill_level);}).length,unplayedN=plan.unplayed.filter(Boolean).length;
    // One line per unplayed opponent (up to 3): our best-supported remaining player and WHY. A shared-only
    // pick is labelled as one unordered candidate, never "best" (GPT audit #84 P2).
    var sends=[];w.blocks.forEach(function(b,j){
      if(!plan.unplayed[j]||sends.length>=3) return;
      var s=plan.sends[j];
      if(!s.length){sends.push("vs "+b.opponent.name+": no evidence-backed option left");return;}
      var r=s[0],direct=r.category!=="I";
      var tied=direct&&s.length>1&&s[1].rank===r.rank;
      sends.push("vs "+b.opponent.name+": "+r.member.name+" — "+(direct?r.cell+" direct"+(tied?" (tied with "+s[1].member.name+")":""):(function(n){return n===1?"≈ shared-opponent only (the only shared-opponent candidate)":"≈ shared-opponent only (one of "+n+" unordered candidates)";})(s.filter(function(x){return x.category==="I";}).length)));
    });
    var riskNames=w.theirs.filter(function(o,j){return plan.unplayed[j]&&plan.sends[j].filter(function(r){return r.category==="G";}).length===0;})
      .map(function(o){return o.name;});
    el.innerHTML='<h2>Tonight</h2>'
      +(f?'<div class="when">'+esc(f.date_status==="ok"?f.local_display:"Undated fixture")+'</div>':'<div class="when">Teams picked by hand — not a Match Day fixture</div>')
      +'<div class="vs"><b>'+esc(ta.name)+'</b>'+(ctx?' ('+(ctx.ourSide==="home"?"home":"away")+')':'')+' vs <b>'+esc(tb.name)+'</b> · '+esc(fmtLabel(w.format))+(f?' · Venue: '+esc(f.location||"No data"):'')+'</div>'
      +wrNextSendCard(w,plan)
      +'<div class="tonight-grid decide">'
      +'<div class="decide-sends"><b>Best sends now</b>'+(sends.length?sends.map(function(x){return '<span>'+esc(x)+'</span>';}).join(''):'<span>Every opponent has played.</span>')+'</div>'
      +'<div class="decide-threats"><b>Dangerous opponents</b>'+(plan.threats.length?plan.threats.map(function(t){return '<span>'+esc(t.opponent.name+" — "+wlText(t.their_wins,t.their_games)+" vs our roster ("+plural(t.their_games,"meeting")+")")+'</span>';}).join(''):'<span>None with a winning recorded record vs us</span>')+'</div>'
      +'<div class="decide-risks"><b>Open risks</b>'+(riskNames.length?'<span>No favorable direct option left vs '+esc(riskNames.join(", "))+'</span>':'<span>None — every unplayed opponent still has a favorable direct option</span>')+'</div>'
      +'</div><p class="muted ns-foot">Next Send uses recorded results only — not odds. "✓ Sent" marks our player Played and the opponent played (Lineup Lab).</p><div class="tonight-grid detail">'
      +'<div><b>Our team</b><span>Remaining: '+remN+' of '+w.ours.length+'</span><span>Available: '+av.Available+'</span><span>Unavailable: '+av.Unavailable+'</span>'
      +'<span>Unknown: '+av.Unknown+' (not the same as unavailable)</span><span>Already used: '+used+' · planned: '+planned+'</span></div>'
      +'<div><b>Evidence across all pairings</b><span>Favorable direct record (any sample size): '+cat.G+'</span><span>Concerning (more direct losses than wins): '+cat.R+'</span>'
      +'<span>Limited evidence: '+cat.E+' even direct · '+cat.I+' shared-opponent only</span><span>Insufficient evidence (nothing recorded): '+cat.X+'</span></div>'
      +'<div><b>Opponent roster</b><span>'+w.theirs.length+' players</span><span>Missing information: '+noSL+' player(s) without a captured SL · '+unplayedN+' not yet played</span></div>'
      +'</div><div class="tonight-links"><a href="#team-section">Open the War Room ↓</a><a href="#lineup-lab">Lineup Lab</a><a href="#match-day-card">Change matchup</a></div>';
  }
  function wrClear(){var t=document.getElementById("tonight");if(t) t.innerHTML=WR_TONIGHT_NOTE?'<h2>Tonight</h2>'
      +(WR_TONIGHT_NOTE.when?'<div class="when">'+esc(WR_TONIGHT_NOTE.when)+'</div>':'')+'<div class="vs">'+esc(WR_TONIGHT_NOTE.text)+'</div>'
      +'<p class="muted">Following Match Day — nothing to plan until it names one fixture with an opponent roster.</p>'
      +'<div class="tonight-links"><a href="#match-day-card">Change matchup</a></div>':"";["wr-opportunities","wr-risks","wr-matrix","lineup-lab","scouting-cards","wr-meetings"].forEach(function(id){var el=document.getElementById(id);if(el) el.innerHTML="";});}

  function renderWarRoom(ta,tb,fmt){
    var opEl=document.getElementById("wr-opportunities");
    if(!opEl) return;
    if(!ta){wrClear();return;}
    if(!tb||!ta.players.length||!tb.players.length){
      wrClear();
      opEl.innerHTML='<h2>Best sends</h2><p class="muted">'+(!tb?'No opponent roster for the selected fixture — choose a fixture with a rostered opponent on Match Day, or pick an opponent team above.':'One of these rosters has no current players captured.')+'</p>';
      return;
    }
    var w=warRoomPair(ta,tb,fmt),plan=wrPlan(w,ta,tb);
    wrTonight(w,plan,ta,tb);
    // Best sends (ranking order, sendable + remaining, unplayed opponents)
    opEl.innerHTML='<h2>Best sends — top opportunities per opponent</h2>'
      +'<p class="muted">Favorable direct records first, then even direct, then indirect-only evidence (not ordered among themselves). Our remaining players only (your Lineup Lab marks). Colors describe recorded results — not odds.</p>'
      +'<div class="table-wrap"><table class="send-table"><thead><tr><th>Opponent</th><th>Best-supported sends among our remaining players</th></tr></thead><tbody>'
      +w.blocks.map(function(b,j){
        var cell=!plan.unplayed[j]?'<span class="muted">Already played.</span>'
          :(plan.sends[j].length?plan.sends[j].slice(0,3).map(function(r,k){return '<span class="send">'+wrChip(r.category)+esc((k+1)+". "+r.player+" — "+r.cell)+'</span>';}).join('<span class="sep"> · </span>')
          :'<span class="muted">No favorable, even or indirect evidence among our remaining players.</span>');
        return '<tr'+(plan.unplayed[j]?'':' class="out"')+'><td>'+esc("vs "+b.opponent_label+" · SL "+slText(b.opponent))+'</td><td>'+cell+'</td></tr>';
      }).join("")+'</tbody></table></div>';
    document.getElementById("wr-risks").innerHTML='<h2>Top risks</h2><div class="risk-grid">'
      +'<div><h3>Dangerous opponents</h3><p class="muted">Winning recorded direct records against our roster (unplayed only).</p>'+wrList(plan.threats.map(function(c){return c.threat_text;}),"No unplayed opponent has a winning recorded record against our roster.")+'</div>'
      +'<div><h3>Avoid sends</h3><p class="muted">More direct losses than wins (remaining players vs unplayed opponents).</p>'+wrList(plan.concerning.map(function(c){return c.text;}),"No concerning direct records among remaining pairings.")+'</div>'
      +'<div><h3>Open risks</h3><p class="muted">Unplayed opponents with no favorable direct option left among our remaining players.</p>'+wrList(plan.risks,"None — every unplayed opponent still has a favorable direct option.")+'</div></div>';
    // Matrix
    var pair=WR_STATE.pair,pairHtml="";
    var head='<tr><th class="corner">Our player ↓ / opponent →</th>'+w.theirs.map(function(o,j){return '<th class="'+(plan.unplayed[j]?'':'out')+'"><a href="#rank-block-'+j+'">'+esc(o.name)+'</a><span class="id-line">SL '+esc(slText(o))+' · ID '+esc(recordIdText(o))+'</span></th>';}).join("")+'</tr>';
    var body=w.matrix.map(function(row,i){
      var m=row.member,out=!plan.rem[String(m.id)];
      return '<tr class="'+(out?'out':'')+'"><th>'+esc(m.name)+'<span class="id-line">SL '+esc(slText(m))+' · ID '+esc(recordIdText(m))+'</span></th>'
        +row.cells.map(function(c,j){
          var on=pair&&pair.our===String(m.id)&&pair.opp===String(w.theirs[j].id);
          if(on) pairHtml=wrPairDetail(w,c,w.blocks[j],fmt);
          return '<td><button type="button" class="mcell cat-'+c.category+(on?' on':'')+(plan.unplayed[j]?'':' out')+'" data-our="'+esc(m.id)+'" data-opp="'+esc(w.theirs[j].id)+'" title="'+esc(WR_CAT_LABELS[c.category]+" — "+c.explanation)+'">'+esc(c.cell)+'</button></td>';
        }).join("")+'</tr>';
    }).join("");
    document.getElementById("wr-matrix").innerHTML='<h2>Matchup matrix</h2>'
      +'<p class="legend"><span class="cat-dot cat-G"></span>Green = more direct wins than losses <span class="cat-dot cat-R"></span>Red = more direct losses than wins <span class="cat-dot cat-E"></span>Yellow = even direct record, or shared-opponent evidence only (≈ ours vs theirs) <span class="cat-dot cat-X"></span>Gray = no evidence. Numbers in () are meetings. Colors describe recorded results only — not odds or predictions. Tap a cell for the evidence behind it.</p>'
      +'<div class="table-wrap"><table class="matrix"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>'
      +'<div id="wr-pair">'+pairHtml+'</div>';
    // Lineup Lab
    var ourRows=w.ours.map(function(m){
      var a=wrAvail(plan.ck,m.id),l=wrLineup(plan.ck,m.id),pid=esc(m.id);
      return '<tr class="'+(plan.rem[String(m.id)]?'':'out')+'"><td>'+esc(playerRef(m))+'</td><td>'+esc(slText(m))+'</td>'
        +'<td><select class="plan" data-plan="avail" data-pid="'+pid+'" aria-label="Availability for '+esc(m.name)+'">'+["Unknown","Available","Unavailable"].map(function(v){return '<option'+(v===a?' selected':'')+'>'+v+'</option>';}).join("")+'</select><span class="print-only">'+esc(a)+'</span></td>'
        +'<td><select class="plan" data-plan="lineup" data-pid="'+pid+'" aria-label="Lineup for '+esc(m.name)+'">'+[["","—"],["Planned","Planned"],["Played","Played"]].map(function(v){return '<option value="'+v[0]+'"'+(v[0]===l?' selected':'')+'>'+v[1]+'</option>';}).join("")+'</select><span class="print-only">'+esc(l||"—")+'</span></td></tr>';
    }).join("");
    var oppRows=w.theirs.map(function(o,j){
      return '<tr class="'+(plan.unplayed[j]?'':'out')+'"><td>'+esc(playerRef(o))+'</td><td>'+esc(slText(o))+'</td><td><label class="inline"><input type="checkbox" class="plan" data-plan="played" data-pid="'+esc(o.id)+'"'+(plan.unplayed[j]?'':' checked')+'> Played</label><span class="print-only">'+(plan.unplayed[j]?'—':'Played')+'</span></td></tr>';
    }).join("");
    var cap=WR_PLAN.cap[ta.key];
    document.getElementById("lineup-lab").innerHTML='<div class="card-head"><h2>Lineup Lab</h2><button type="button" class="secondary" id="ll-clear">Clear marks for this fixture</button></div>'
      +'<p class="muted" id="ll-context">'+esc(wrCtxLabel(ta,tb))+' Marks change which candidates count as remaining — never the evidence. Unknown is not Unavailable. Coach notes follow the opponent player to every fixture.</p>'
      +'<div class="grid"><div><h3>Our team</h3><div class="table-wrap"><table><thead><tr><th>Player (APA record ID)</th><th>SL</th><th>Availability</th><th>Lineup</th></tr></thead><tbody>'+ourRows+'</tbody></table></div></div>'
      +'<div><h3>Opponent</h3><div class="table-wrap"><table><thead><tr><th>Player (APA record ID)</th><th>SL</th><th>Already played</th></tr></thead><tbody>'+oppRows+'</tbody></table></div></div></div>'
      +'<h3>Snapshot</h3><dl class="matchup-facts">'+plan.metrics.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join("")+'</dl>'
      +'<label class="cap-label">Reference skill cap (optional, user-entered)<input type="number" id="ll-cap" min="1" max="99" value="'+(cap?esc(cap):'')+'" placeholder="none — no default is assumed"></label>'
      +'<h3>Best remaining sends — and why</h3><p class="muted">For each unplayed opponent: our best-supported remaining player and the recorded evidence behind it. Not odds.</p>'
      +wrList(w.blocks.map(function(b,j){return plan.unplayed[j]?"vs "+b.opponent_label+": "+(plan.sends[j].length?"best-supported send: "+plan.sends[j][0].player+" — reason: "+plan.sends[j][0].reason:"no evidence-backed option left among our remaining players"):null;}).filter(Boolean),"Every opponent has already played.")
      +'<h3>Protected players — unique favorable options (consider saving)</h3><p class="muted">The only remaining favorable direct option against an unplayed opponent.</p>'+wrList(plan.unique,"None right now.");
    // Scouting cards
    document.getElementById("scouting-cards").innerHTML='<h2>Opponent scouting cards</h2><p class="muted">Recorded facts per opponent. No meetings with our roster is unknown — never a weakness. Coach observations are your notes (this browser only).</p><div class="scout-grid">'
      +w.cards.map(function(c,j){
        var pid=esc(c.opponent.id),cc=wrCoach(c.opponent.id),played=!plan.unplayed[j];
        var tagSel=function(field){return '<select class="plan" data-plan="'+field+'" data-pid="'+pid+'" aria-label="Coach tag"><option value="">—</option>'
          +WR_COACH_TAGS.map(function(t){return '<option'+(cc[field==="tag1"?"t1":"t2"]===t?' selected':'')+'>'+esc(t)+'</option>';}).join("")+'</select>';};
        var f=[["Team record",c.team_record],["League lifetime",c.lifetime],["Recorded games",c.sample],["Vs our roster",c.vs_ours],["Meetings with our players",c.met_list],["Shared-opponent evidence",c.shared_summary],["Record by opponent SL",c.by_sl],["Winning records vs",c.winning_sl],["Losing records vs",c.losing_sl],["Missing information",c.missing]];
        return '<div class="scout'+(played?' out':'')+'"><div class="scout-head">'+esc(c.label)+' · SL '+esc(c.sl)+(played?' · already played':'')+'</div><dl>'
          +f.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join("")
          +'<dt>Coach observations</dt><dd><span class="muted">Your opinion, not APA facts.</span> '+tagSel("tag1")+' '+tagSel("tag2")
          +'<textarea class="plan" data-plan="note" data-pid="'+pid+'" rows="2" placeholder="What you saw">'+esc(cc.n||"")+'</textarea>'
          +'<div class="coach-summary">'+esc(wrCoachSummary(c.opponent.id))+'</div></dd></dl></div>';
      }).join("")+'</div>';
    // Meetings
    document.getElementById("wr-meetings").innerHTML='<h2>Direct meetings between the rosters</h2>'+(w.meetings.length
      ?'<p class="muted">Newest first · dates in '+esc(WR_TZ)+'.</p><div class="table-wrap"><table><thead><tr><th>Date</th><th>Our player</th><th>Opponent</th><th>Result (ours)</th><th>SL ours/theirs</th><th>Session</th></tr></thead><tbody>'
        +w.meetings.slice(0,60).map(function(g){return '<tr><td>'+esc(g.date)+'</td><td>'+esc(playerRef(g.our))+'</td><td>'+esc(playerRef(g.opp))+'</td><td>'+esc(g.result)+'</td><td>'+esc((wrKnown(g.own_sl)?g.own_sl:"—")+" / "+(wrKnown(g.opp_sl)?g.opp_sl:"—"))+'</td><td>'+esc(g.session)+'</td></tr>';}).join("")+'</tbody></table></div>'
        +(w.meetings.length>60?'<p class="muted">Showing the newest 60 of '+w.meetings.length+'; Player vs Player lists every meeting.</p>':'')
      :'<p class="muted">No recorded direct meetings between these rosters in '+esc(fmtLabel(fmt))+'.</p>');
  }
  function wrCtxLabel(ta,tb){
    var c=MATCHUP_CONTEXT;
    if(c&&c.ourKey===ta.key&&c.oppKey===tb.key&&c.fixture) return "Marks for this fixture only ("+(c.fixture.local_display||"undated fixture")+"), saved in this browser.";
    return "Teams picked by hand — not a Match Day fixture. Marks here are kept apart from every fixture's marks.";
  }
  function wrPairDetail(w,row,block,fmt){
    var m=row.member,o=block.opponent,mm=oppMap(m.id,fmt),om=oppMap(o.id,fmt);
    var shared=Object.keys(mm).filter(function(k){return !!om[k];}).sort(function(a,b){var d=(mm[b].g+om[b].g)-(mm[a].g+om[a].g);if(d) return d;var na=PLAYERS[a]?PLAYERS[a].name:a,nb=PLAYERS[b]?PLAYERS[b].name:b;return na<nb?-1:(na>nb?1:0);});
    var games=w.meetings.filter(function(g){return String(g.our.id)===String(m.id)&&String(g.opp.id)===String(o.id);});
    return '<div class="pair cat-border-'+row.category+'"><h3>'+esc(playerRef(m))+' vs '+esc(playerRef(o))+'</h3>'
      +'<p>'+wrChip(row.category)+' <b>'+esc(WR_CAT_LABELS[row.category])+'</b> · rank '+esc(row.rank)+' of '+block.rows.length+' vs this opponent · '+esc(row.explanation)+'</p>'
      +(games.length?'<h4>Direct meetings</h4><div class="table-wrap"><table><thead><tr><th>Date</th><th>Result (ours)</th><th>SL ours/theirs</th><th>Session</th></tr></thead><tbody>'+games.map(function(g){return '<tr><td>'+esc(g.date)+'</td><td>'+esc(g.result)+'</td><td>'+esc((wrKnown(g.own_sl)?g.own_sl:"—")+" / "+(wrKnown(g.opp_sl)?g.opp_sl:"—"))+'</td><td>'+esc(g.session)+'</td></tr>';}).join("")+'</tbody></table></div>':'<p class="muted">No direct meetings.</p>')
      +(shared.length?'<h4>Shared opponents ('+shared.length+')</h4><div class="table-wrap"><table><thead><tr><th>Shared opponent</th><th>'+esc(m.name)+' vs them</th><th>'+esc(o.name)+' vs them</th></tr></thead><tbody>'
        +shared.slice(0,25).map(function(k){return '<tr><td>'+esc(PLAYERS[k]?playerRef(PLAYERS[k]):k)+'</td><td>'+esc(wlText(mm[k].w,mm[k].g)+" ("+plural(mm[k].g,"game")+")")+'</td><td>'+esc(wlText(om[k].w,om[k].g)+" ("+plural(om[k].g,"game")+")")+'</td></tr>';}).join("")+'</tbody></table></div>'
        +(shared.length>25?'<p class="muted">Showing 25 of '+shared.length+' (largest combined samples).</p>':''):'<p class="muted">No shared opponents.</p>')
      +'</div>';
  }
  (function(){
    var root=document.getElementById("matchup-print");
    if(!root) return;
    function current(){return {ta:TEAM_INDEX[TA.value],tb:TEAM_INDEX[TB.value]};}
    root.addEventListener("change",function(ev){
      var t=ev.target,k=t&&t.getAttribute&&t.getAttribute("data-plan"),cur=current();
      if(t&&t.id==="ll-cap"&&cur.ta){var v=parseFloat(t.value);if(isFinite(v)&&v>0) WR_PLAN.cap[cur.ta.key]=v; else delete WR_PLAN.cap[cur.ta.key];wrSave();renderTeamMatchups();return;}
      if((k==="tag1"||k==="tag2")&&t.getAttribute("data-pid")){
        wrSetCoach(t.getAttribute("data-pid"),k==="tag1"?"t1":"t2",t.value);
        var sbox=t.parentNode.querySelector(".coach-summary");if(sbox) sbox.textContent=wrCoachSummary(t.getAttribute("data-pid"));
        return;
      }
      if(!k||!cur.ta||!cur.tb) return;
      var pid=t.getAttribute("data-pid"),ck=wrCtx(cur.ta,cur.tb);
      if(k==="avail") wrSetMark("our",ck,pid,"a",t.value==="Unknown"?"":t.value);
      else if(k==="lineup") wrSetMark("our",ck,pid,"l",t.value);
      else if(k==="played") wrSetMark("opp",ck,pid,"p",t.checked?true:"");
      else return;
      renderTeamMatchups();
      var again=root.querySelector('[data-plan="'+k+'"][data-pid="'+pid+'"]');if(again) again.focus();
    });
    root.addEventListener("input",function(ev){
      var t=ev.target,cur=current();
      if(!t||!t.getAttribute||t.getAttribute("data-plan")!=="note"||!cur.tb) return;
      var npid=t.getAttribute("data-pid");
      wrSetCoach(npid,"n",t.value);
      var box=t.parentNode.querySelector(".coach-summary");if(box) box.textContent=wrCoachSummary(npid);
    });
    root.addEventListener("click",function(ev){
      var t=ev.target&&ev.target.closest?ev.target.closest("button"):null;
      if(!t) return;
      var cur=current();
      if(t.id==="ll-clear"&&cur.ta&&cur.tb){var ck=wrCtx(cur.ta,cur.tb);delete WR_PLAN.our[ck];delete WR_PLAN.opp[ck];wrSave();renderTeamMatchups();return;}
      if(t.classList.contains("mcell")){
        var p={our:t.getAttribute("data-our"),opp:t.getAttribute("data-opp")};
        WR_STATE.pair=(WR_STATE.pair&&WR_STATE.pair.our===p.our&&WR_STATE.pair.opp===p.opp)?null:p;
        renderTeamMatchups();
        var d=document.getElementById("wr-pair");if(d&&d.scrollIntoView&&WR_STATE.pair) d.scrollIntoView({block:"nearest"});
      }
    });
  })();
  // Next Send: pick the opponent they put up; "Mark sent" records the pairing as played (planning marks only).
  (function(){
    var el=document.getElementById("tonight");
    if(!el) return;
    el.addEventListener("click",function(ev){
      var t=ev.target&&ev.target.closest?ev.target.closest("button"):null;
      if(!t) return;
      var ta=TEAM_INDEX[TA.value],tb=TEAM_INDEX[TB.value];
      if(t.hasAttribute("data-next")){WR_STATE.next=t.getAttribute("data-next");renderTeamMatchups();
        var again=el.querySelector('.ns-chip.on');if(again) again.focus();return;}
      if(t.hasAttribute("data-send-our")&&ta&&tb){var ck=wrCtx(ta,tb);
        wrSetMark("our",ck,t.getAttribute("data-send-our"),"l","Played");wrSetMark("opp",ck,t.getAttribute("data-send-opp"),"p",true);
        WR_STATE.next=null;renderTeamMatchups();}
    });
  })();
  // "Start here" opens on a first visit; once closed it stays closed on this device.
  (function(){
    var sh=document.getElementById("start-here"),key="ultimate-coach:start-here-closed";
    if(!sh) return;
    try{if(window.localStorage.getItem(key)==="1") sh.removeAttribute("open");}catch(e){}
    sh.addEventListener("toggle",function(){try{if(sh.open) window.localStorage.removeItem(key); else window.localStorage.setItem(key,"1");}catch(e){}});
  })();
