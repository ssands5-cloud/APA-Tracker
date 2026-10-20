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
  // Matrix view: "evidence" (full cell text, same as Excel) or "captain" (🟢🟡⚪🔴 + record). Remembered on this device.
  var WR_VIEW=(function(){try{return window.localStorage.getItem("ultimate-coach:matrix-view")==="captain"?"captain":"evidence";}catch(e){return "evidence";}})();
  var WR_CAPTAIN_ICON={G:"🟢",E:"🟡",I:"🟡",X:"⚪",R:"🔴"};
  function wrCaptainCell(c){return WR_CAPTAIN_ICON[wrCategory(c.c)]+(c.c&&c.c.direct?" "+wlText(c.c.direct.w,c.c.direct.g):(wrCategory(c.c)==="I"?" ≈":""));}
  // Set by Match Day when its current selection has no fixture to follow (no date, no match, bye,
  // opponent without a roster, several fixtures awaiting a choice, no team): {when, text}. The Tonight
  // panel then states that instead of going blank or keeping a previous fixture (GPT audit #84).
  var WR_TONIGHT_NOTE=null;
  function wrKnown(x){return x!==null&&x!==undefined;}
  function wrHistoricalSLText(x){return typeof x==="number"&&isFinite(x)&&x>0?String(x):"not captured";}
  function wrCategory(c){if(c.direct){var w=c.direct.w,l=c.direct.g-w;return w>l?"G":(w<l?"R":"E");}return c.shared?"I":"X";}
  function wrCell(c){
    if(c.direct) return wlText(c.direct.w,c.direct.g)+" ("+c.direct.g+")";
    if(c.shared) return "≈ "+wlText(c.ow,c.og)+" vs "+wlText(c.tw,c.tg)+" ("+c.shared+" shared)";
    return "No verified evidence";
  }
  function wrExplain(c){
    return [c.direct?"Direct: "+wlText(c.direct.w,c.direct.g)+" in "+plural(c.direct.g,"meeting"):"No verified direct meetings in this snapshot",
      c.shared?"Indirect: "+plural(c.shared,"shared opponent")+" — ours "+wlText(c.ow,c.og)+" ("+plural(c.og,"game")+"), theirs "+wlText(c.tw,c.tg)+" ("+plural(c.tg,"game")+")":"no shared opponents"].join(" · ");
  }
  var WR_CAT_WORD={G:"favorable",R:"concerning",E:"even"};
  // Why a player appears as a send (mirrors analytics.ultimate_coach_war_room.reason).
  function wrReason(c){
    if(c.direct) return wlText(c.direct.w,c.direct.g)+" direct record ("+plural(c.direct.g,"meeting")+") — "+WR_CAT_WORD[wrCategory(c)]+(c.direct.g<3?" · small sample":"");
    if(c.shared) return "shared-opponent results only: ours "+wlText(c.ow,c.og)+" vs theirs "+wlText(c.tw,c.tg)+" across "+plural(c.shared,"shared opponent")+" (no verified direct meetings in this snapshot)";
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
    function lab(e){return "SL"+Math.trunc(e.sl)+" ("+wlText(e.w,e.g)+", "+plural(e.g,"meeting")+(e.g<3?", small sample":"")+")";}
    return [known.map(function(e){return "vs SL"+Math.trunc(e.sl)+" "+wlText(e.w,e.g)+" ("+plural(e.g,"meeting")+(e.g<3?", small sample":"")+")";}).join(" · "),
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
  // Facts-only one-liner for the top of a scouting card (mirrors analytics quick_read).
  // ---- Quick read badges: icon + a few words, above the dense sentence below (mirrors
  // analytics.quick_read_badges). Paul's own spec -- a captain reads these without stopping.
  // GPT audit correction (d3203ee): filtering to category G/E only made an opponent with
  // nothing but CONCERNING (R) direct records -- real games we lost -- show "No evidence on
  // our roster", which is false. Uses c.their_games, the SAME total wrQuickRead's own
  // "Threat:/Even:/Vs our roster:" line already shows (every direct row, any result). Also
  // drops "Strong/Limited" adjectives for the actual count: three meetings does not earn the
  // word "strong".
  function wrQuickReadBadges(c,b,hasNote){
    var tg=c.their_games,badges=[];
    if(tg){
      badges.push((tg>=3?"":"⚠ ")+"Direct meetings vs roster: "+plural(tg,"meeting")+(tg>=3?"":" (small sample)"));
    } else {
      var shared=b.rows.filter(function(r){return r.category==="I";});
      if(shared.length){
        var total=shared.reduce(function(a,r){return a+r.c.shared;},0),strong=shared.length>=3||total>=6;
        badges.push((strong?"✅ ":"⚠ ")+"Shared-opponent evidence: "+plural(shared.length,"player")+", "+plural(total,"opponent link")+(strong?"":" (thin)"));
      } else badges.push("⚠ No evidence on our roster");
    }
    if(c.losing_sl!=="—"&&c.losing_sl!=="None recorded") badges.push("⚠ Recorded losses vs "+c.losing_sl);
    if(!hasNote) badges.push("❓ No coach observations");
    return badges;
  }

  function wrQuickRead(c,b){
    var tw=c.their_wins,tg=c.their_games,parts=[];
    if(!tg) parts.push("Unknown vs our roster — no meetings (not weak)");
    else parts.push((tw>tg-tw?"Winning direct record":(2*tw===tg?"Even":"Vs our roster"))+": "+wlText(tw,tg)+" vs our roster ("+plural(tg,"meeting")+(tg<3?", small sample":"")+")");
    var roster=b.rows.map(function(r){return r.member;});
    var names=function(g){return g.map(function(r){return wrDisplayName(r.member,roster);}).join(", ");},done=false;
    [["G","Direct-record order #1"],["E","Even option on record"]].forEach(function(x){
      if(done) return;var g=b.rows.filter(function(r){return r.category===x[0];});if(!g.length) return;
      var top=g.filter(function(r){return String(r.rank).replace("=","")===String(g[0].rank).replace("=","");});
      parts.push(x[1]+": "+names(top)+" ("+wlText(top[0].c.direct.w,top[0].c.direct.g)+", "+plural(top[0].c.direct.g,"meeting")+(top[0].c.direct.g<3?", small sample":"")+(top.length>1?", tied":"")+")");
      var contexts=top.map(function(r){return r.sl_context;}).filter(function(x,i,a){return x&&a.indexOf(x)===i;}).sort();
      if(contexts.length) parts.push(top.length===1?contexts[0]:"Meeting SLs differ or are missing; check each pairing's detail");done=true;});
    if(!done){var sh=b.rows.filter(function(r){return r.category==="I";}).length;
      parts.push(sh?"No direct answer — "+plural(sh,"shared-opponent candidate")+" (≈, not ordered)":"No evidence-backed answer on our roster");}
    var av=b.rows.filter(function(r){return r.category==="R";});
    if(av.length) parts.push("Losing direct records: "+av.map(function(r){return wrDisplayName(r.member,roster)+" ("+wlText(r.c.direct.w,r.c.direct.g)+", "+plural(r.c.direct.g,"meeting")+(r.c.direct.g<3?", small sample":"")+")";}).join(", "));
    if(c.winning_sl!=="—"&&c.winning_sl!=="None recorded") parts.push("Winning records vs "+c.winning_sl);
    if(c.losing_sl!=="—"&&c.losing_sl!=="None recorded") parts.push("Losing records vs "+c.losing_sl);
    return parts.join(" · ");
  }
  function wrMeetingSLContext(games,rosterSL){
    if(!games.length) return "";
    var capturedLevel=function(x){return typeof x==="number"&&isFinite(x)&&x>0?x:null;};
    rosterSL=capturedLevel(rosterSL);
    var seen={},missing=false;games.forEach(function(g){var sl=capturedLevel(g.opp_sl);if(sl===null) missing=true;else seen[sl]=true;});
    var levels=Object.keys(seen).map(Number).sort(function(a,b){return a-b;});
    if(!levels.length) return "Meeting opponent SL not captured";
    if(wrKnown(rosterSL)&&levels.every(function(sl){return sl===rosterSL;})&&!missing) return "";
    return "Meeting opponent SL "+levels.join(", ")+"; roster capture SL "+(wrKnown(rosterSL)?rosterSL:"not captured")+(missing?"; some meeting SLs not captured":"");
  }
  function wrMeetingDateContext(games){
    var times=games.map(function(g){return wrInstant(val(g,"match_date"));});
    var known=times.filter(function(t){return t!==null;});
    if(!known.length) return "Meeting dates not captured";
    var label=wrDayLabel(known.reduce(function(latest,t){return t>latest?t:latest;},known[0]));
    if(label==="No data") return "Meeting dates not captured";
    return "Latest dated meeting: "+label+(known.length!==times.length?"; some meeting dates not captured":"");
  }
  // ---- Captain confidence level (mirrors analytics/ultimate_coach_confidence.py exactly) ----
  var WR_LEVEL_POINTS={Strong:6,Solid:3,Thin:1,Unknown:0,Conflicted:0,Caution:-3};
  function wrOverall(p,fmt){var c=careerComplete(((p&&p.career_stats)||[]).filter(function(r){return r.format===fmt;}));return [c.w,c.g];}
  function wrFormCmp(own,opp,edge){
    var num=(own[0]+5)*(opp[1]+10)-(opp[0]+5)*(own[1]+10),den=(own[1]+10)*(opp[1]+10),d=20*num-edge*den;
    return d>0?1:d<0?-1:0;
  }
  function wrMeetingWord(g){return plural(g,"meeting");}
  function wrPairConfidence(direct,own,opp,shared,slChanged){
    var known=own[1]>=20&&opp[1]>=20;
    var fFor=known&&wrFormCmp(own,opp,1)>=0,fAgainst=known&&wrFormCmp(opp,own,1)>=0,fStrong=known&&wrFormCmp(own,opp,3)>=0;
    var overall="overall "+wlText(own[0],own[1])+" vs "+wlText(opp[0],opp[1]);
    function out(level,why){return {level:level,points:WR_LEVEL_POINTS[level],why:why,text:level+" — "+why};}
    if(direct&&direct.g>0){
      var w=direct.w,g=direct.g,rec=wlText(w,g)+" in "+wrMeetingWord(g),fav=w>g-w,unf=w<g-w,level,why;
      if(fav&&fAgainst) return out("Conflicted",rec+", but a weaker "+overall);
      if(unf&&fFor) return out("Conflicted",rec+", but a stronger "+overall);
      if(unf) return out("Caution",rec+" direct");
      if(!fav){level="Thin";why="even direct record, "+rec;}
      else if(g>=5&&w/g>=0.7||g>=3&&fFor){level="Strong";why=rec+(fFor?" and a stronger "+overall:"");}
      else if(g>=3||fFor){level="Solid";why=rec+(fFor?" and a stronger "+overall:"");}
      else {level="Thin";why="only "+rec;}
      if(slChanged&&(level==="Strong"||level==="Solid")){level=level==="Strong"?"Solid":"Thin";why+="; skill levels changed since they last met";}
      return out(level,why);
    }
    if(fStrong) return out("Strong","no direct history; much stronger "+overall);
    if(fFor) return out("Solid","no direct history; stronger "+overall);
    if(fAgainst) return out("Caution","no direct history; weaker "+overall);
    if(shared&&shared.og>0&&shared.tg>0){
      var n=shared.n,cross=10*(shared.ow*shared.tg-shared.tw*shared.og),lim=shared.og*shared.tg;
      var common=plural(n,"shared opponent")+": ours "+wlText(shared.ow,shared.og)+", theirs "+wlText(shared.tw,shared.tg);
      if(cross>=lim) return out(n>=3?"Solid":"Thin",common);
      if(cross<=-lim) return out("Caution",common);
    }
    return out("Unknown","no direct history and no clear overall or shared-opponent edge");
  }
  function wrSlChanged(games,ownSL,oppSL){
    var known=function(x){return typeof x==="number"&&isFinite(x)&&x>0;};
    var dated=games.filter(function(g){return wrInstant(val(g,"match_date"))!==null;});
    if(!dated.length||!known(ownSL)||!known(oppSL)) return false;
    var last=dated.reduce(function(a,b){return wrInstant(val(b,"match_date"))>wrInstant(val(a,"match_date"))?b:a;});
    var ls=val(last,"own_skill_level"),lo=val(last,"opponent_skill_level");
    if(!known(ls)||!known(lo)) return false;
    return ls!==ownSL||lo!==oppSL;
  }
  function warRoomPair(ta,tb,fmt){
    var ours=ta.players.slice().sort(memberOrder),theirs=tb.players.slice().sort(memberOrder);
    var blocks=theirs.map(function(opp){return rankVsOpponent(ours,opp,fmt);});
    blocks.forEach(function(b){b.byMember={};b.rows.forEach(function(r,i){
      r.category=wrCategory(r.c);r.cell=wrCell(r.c);r.explanation=wrExplain(r.c);
      var games=r.c.direct?rowsFor(r.member.id,fmt).filter(function(g){return String(val(g,"opponent_id"))===String(b.opponent.id);}):[];
      r.sl_context=r.c.direct?wrMeetingSLContext(games.map(function(g){return {opp_sl:val(g,"opponent_skill_level")};}),b.opponent.skill_level):"";
      r.date_context=r.c.direct?wrMeetingDateContext(games):"";
      r.reason=wrReason(r.c)+(r.sl_context?" \u00b7 "+r.sl_context:"")+(r.date_context?" \u00b7 "+r.date_context:"");
      r.captain=wrCaptainCell(r);r.position=i+1;b.byMember[String(r.member.id)]=r;
      r.confidence=wrPairConfidence(r.c.direct,wrOverall(PLAYERS[String(r.member.id)],fmt),wrOverall(PLAYERS[String(b.opponent.id)],fmt),
        r.c.shared?{ow:r.c.ow,og:r.c.og,tw:r.c.tw,tg:r.c.tg,n:r.c.shared}:null,
        r.c.direct?wrSlChanged(games,r.member.skill_level,b.opponent.skill_level):false);
    });});
    var matrix=ours.map(function(m){return {member:m,cells:blocks.map(function(b){return b.byMember[String(m.id)];})};});
    var concerning=[];
    blocks.forEach(function(b,j){b.rows.forEach(function(r){if(r.category!=="R") return;var w=r.c.direct.w,g=r.c.direct.g;
      concerning.push({our:r.member,opp:b.opponent,j:j,w:w,g:g,text:r.player+" vs "+b.opponent_label+": "+wlText(w,g)+" direct ("+plural(g,"meeting")+")"+(g<3?" · SMALL SAMPLE":"")+(g===1?" · Lost once":"")});});});
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
    cards.forEach(function(c,j){c.quick_read=wrQuickRead(c,blocks[j]);});
    var threats=cards.filter(function(c){return c.their_games&&c.their_wins>c.their_games-c.their_wins;});
    threats.sort(function(x,y){var a=2*x.their_wins-x.their_games,b=2*y.their_wins-y.their_games;if(a!==b) return b-a;
      if(x.their_wins!==y.their_wins) return y.their_wins-x.their_wins;if(x.their_games!==y.their_games) return y.their_games-x.their_games;return memberOrder(x.opponent,y.opponent);});
    threats.forEach(function(c){c.threat_text=c.label+" · SL "+c.sl+" · "+wlText(c.their_wins,c.their_games)+" vs our roster ("+plural(c.their_games,"meeting")+", "+c.players_met+" of our players)"+(c.their_games<3?" · small sample":"");});
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
    return {matrix:w.matrix.map(function(r){return r.cells.map(function(c){return [c.category,c.cell,c.explanation,c.reason,c.captain];});}),
      best:w.blocks.map(function(b){return b.rows.filter(function(r){return WR_SENDABLE[r.category];}).map(function(r){return r.player;});}),
      concerning:w.concerning.map(function(c){return c.text;}),threats:w.threats.map(function(c){return c.threat_text;}),
      cards:w.cards.map(function(c){return [c.quick_read,c.sl,c.team_record,c.lifetime,c.sample,c.vs_ours,c.met_list,c.shared_summary,c.by_sl,c.winning_sl,c.losing_sl,c.missing];}),
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
  var WR_PLAN_READ_FAILED=false,WR_PLAN_SAVE_FAILED=false,WR_PLAN_CHANGED_ELSEWHERE=false,WR_PLAN_SAVED=null;
  var WR_PLAN=(function(){
    var o=null;try{WR_PLAN_SAVED=window.localStorage.getItem("ultimate-coach:plan-v2");o=JSON.parse(WR_PLAN_SAVED||"null");}catch(e){o=null;WR_PLAN_READ_FAILED=true;}
    var p=(o&&typeof o==="object")?{our:o.our||{},opp:o.opp||{},notes:o.notes||{},cap:o.cap||{},coach:o.coach||{},archive:o.archive||{}}:{our:{},opp:{},notes:{},cap:{},coach:{},archive:{}};
    // Every distinct legacy observation is preserved (GPT audit #84): the first fills an empty note; any other,
    // different one (another team scope, or a note that already exists) is archived with its scope. The archive
    // is shown on the card as an earlier opinion and is never copied back into the editable note.
    Object.keys(p.notes).forEach(function(scope){var s=p.notes[scope]||{};Object.keys(s).forEach(function(pid){
      var n=String((s[pid]&&s[pid].n)||"").trim();if(!n) return;
      var c=p.coach[pid]||(p.coach[pid]={});
      if(!c.n){c.n=n;return;}
      if(String(c.n).trim()===n) return;
      var a=p.archive[pid]||(p.archive[pid]=[]);
      if(!a.some(function(x){return x.n===n;})) a.push({scope:scope,n:n});
    });});
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
  // First-screen coach note: one line; a longer note opens to its full text (GPT audit #84: a long
  // observation must not push Risks off a phone screen, and must stay reachable).
  function wrNotePreview(n,label){
    if(!n) return "";
    var full=n+" ("+label+")";
    if(n.length<=48) return '<span class="note-line">📝 '+esc(full)+'</span>';
    return '<details class="note-more"><summary>📝 '+esc(n.slice(0,36).replace(/\s+\S*$/,""))+'… <span class="muted">('+esc(label)+')</span></summary>'+esc(n)+'</details>';
  }
  // GPT audit (issue #84, NOTES-01): a note-flag rendered at full-render time only went stale the
  // moment a captain typed and blurred a new observation -- the flag they just created would not
  // appear anywhere (matrix header, Tonight, Lineup Lab, the opportunities table) until something
  // else forced a full re-render. Same authorization as the scouting card's own live "No coach
  // observations" badge below: note PRESENCE is metadata about the opinion, not evidence it could
  // corrupt, so every occurrence of it is kept live via a stable slot, patched by pid on input.
  function wrNoteFlagHtml(pid,kind,label){
    var n=wrCoachSummary(pid);
    if(!n) return "";
    if(kind==="icon") return '<a class="note-flag" href="#coach-note-'+esc(pid)+'" aria-label="Read Coach Observation" style="display:inline-flex;min-width:44px;min-height:44px;align-items:center;justify-content:center" title="'+esc(n+" (your opinion, not APA facts)")+'">📝</a>';
    if(kind==="preview-space") return ' <span>'+wrNotePreview(n,label)+'</span>';
    if(kind==="dot") return ' · 📝 '+esc(n)+' (your opinion, not APA facts)';
    if(kind==="card") return '📝 '+esc(n+" (your opinion, not APA facts)");
    return '<span>'+wrNotePreview(n,label)+'</span>';
  }
  // GPT audit (issue #84, NOTES-01 follow-up): "empty wrappers are implementation work, not an
  // owner-review gate" -- a box-styled wrapper (Next Send's and the scouting card's own note
  // box) is always present in the DOM so it can be patched live, hidden via style when there is
  // no note so an empty colored box never shows, same as a bare icon/text slot shows nothing.
  function wrNoteFlagSlot(pid,kind,label,tag,cls){
    tag=tag||"span";
    var html=wrNoteFlagHtml(pid,kind,label);
    return '<'+tag+' class="note-flag-slot'+(cls?" "+cls:"")+'" data-note-pid="'+esc(pid)+'" data-note-kind="'+esc(kind)+'" data-note-label="'+esc(label||"")+'"'+(html?"":' style="display:none"')+'>'+html+'</'+tag+'>';
  }
  function wrPatchNoteFlags(pid){
    document.querySelectorAll(".note-flag-slot").forEach(function(s){
      if(s.getAttribute("data-note-pid")===String(pid)){
        var html=wrNoteFlagHtml(pid,s.getAttribute("data-note-kind"),s.getAttribute("data-note-label"));
        s.innerHTML=html;
        s.style.display=html?"":"none";
      }
    });
  }
  // Tags and free text are both Coach Observation. Patch their opinion metadata only;
  // evidence badges, records, categories and candidate ordering stay untouched.
  function wrPatchCoachObservation(pid){
    var summary=wrCoachSummary(pid),editor=document.getElementById("coach-note-"+pid);
    var scout=editor&&editor.closest?editor.closest(".scout"):null;
    var box=scout?scout.querySelector(".coach-summary"):null;if(box) box.textContent=summary;
    var row=scout?scout.querySelector(".quick-read-badges"):null;
    if(row){
      var spans=row.querySelectorAll("span"),found=null;
      for(var i=0;i<spans.length;i++) if(spans[i].textContent==="\u2753 No coach observations") found=spans[i];
      if(summary&&found) found.remove();
      else if(!summary&&!found){var sp=document.createElement("span");sp.textContent="\u2753 No coach observations";row.appendChild(sp);}
    }
    wrPatchNoteFlags(pid);
  }
  function wrArchiveHtml(pid){
    var a=WR_PLAN.archive[String(pid)]||[];
    if(!a.length) return "";
    return '<div class="coach-archive"><b>Earlier notes kept from the previous version (opinion):</b>'
      +a.map(function(x){var t=TEAM_INDEX[x.scope];return '<div>'+esc(x.n)+' <span class="muted">(noted under '+esc(t?t.name:x.scope)+')</span></div>';}).join("")+'</div>';
  }
  function wrSetCoach(pid,field,value){var c=WR_PLAN.coach[String(pid)]||(WR_PLAN.coach[String(pid)]={});if(value) c[field]=value; else delete c[field];wrSave();}
  function wrStorageMessage(){
    if(WR_PLAN_READ_FAILED) return "Previously saved marks and notes could not be read. Changes last only while this page is open; earlier saved data has not been replaced. Copy any notes before closing, then reopen the page to try again.";
    if(WR_PLAN_CHANGED_ELSEWHERE) return "The saved plan changed elsewhere. Changes here are not saved. Copy any new notes before reloading this page to load the saved plan. Earlier saved data has not been replaced.";
    if(WR_PLAN_SAVE_FAILED) return "Planning changes are not saved. They last only while this page is open. Copy any notes before closing; saving will be tried again on your next edit.";
    return "";
  }
  function wrStorageScope(){return wrStorageMessage()?"Changes last only while this page is open.":"Saved in this browser.";}
  function wrPatchStorageStatus(){
    var message=wrStorageMessage();
    document.querySelectorAll(".wr-save-scope").forEach(function(el){el.textContent=wrStorageScope();});
    if(!message){document.querySelectorAll(".wr-storage-warning").forEach(function(el){el.remove();});return;}
    function show(parent,before,id,announce){
      if(!parent) return;
      var el=document.getElementById(id);
      if(!el){el=document.createElement("p");el.id=id;el.className="wr-storage-warning";
        el.style.cssText="padding:10px;border:1px solid #c58c24;border-radius:6px;background:#fff4d6;color:#5d3d00;overflow-wrap:anywhere";
        if(announce){el.setAttribute("role","status");el.setAttribute("aria-live","polite");}
        parent.insertBefore(el,before||null);}
      if(el.textContent!==message) el.textContent=message;
    }
    ["tonight","lineup-lab"].forEach(function(id){var el=document.getElementById(id);
      if(el&&el.firstChild) show(el,el.firstChild.nextSibling,"wr-storage-"+id,id==="tonight");});
    document.querySelectorAll('textarea[data-plan="note"]').forEach(function(el){
      show(el.parentNode,el,"wr-storage-note-"+el.getAttribute("data-pid"),false);});
  }
  function wrSave(){
    // Protect the saved plan if another page changed the snapshot this page loaded.
    // This is a freshness guard, not a merge or an atomic multi-tab transaction.
    if(!WR_PLAN_READ_FAILED){
      var saved;
      try{saved=window.localStorage.getItem("ultimate-coach:plan-v2");}catch(e){WR_PLAN_READ_FAILED=true;}
      if(!WR_PLAN_READ_FAILED){
        if(saved!==WR_PLAN_SAVED) WR_PLAN_CHANGED_ELSEWHERE=true;
        else try{
          var next=JSON.stringify(WR_PLAN);window.localStorage.setItem("ultimate-coach:plan-v2",next);
          WR_PLAN_SAVED=next;WR_PLAN_SAVE_FAILED=false;WR_PLAN_CHANGED_ELSEWHERE=false;
        }catch(e){WR_PLAN_SAVE_FAILED=true;}
      }
    }
    wrPatchStorageStatus();
  }
  function wrCtx(ta,tb){
    var c=MATCHUP_CONTEXT,fixture="manual";
    if(c&&tb&&c.ourKey===ta.key&&c.oppKey===tb.key&&c.fixture) fixture="fixture:"+String(c.fixture.match_id!==undefined&&c.fixture.match_id!==null?c.fixture.match_id:c.fixture.match_external_id);
    return ta.key+"||"+(tb?tb.key:"")+"||"+fixture;
  }
  function wrMark(kind,scope,pid){var s=WR_PLAN[kind][scope];return (s&&s[String(pid)])||{};}
  function wrSetMark(kind,scope,pid,field,value,deferSave){var s=WR_PLAN[kind][scope]||(WR_PLAN[kind][scope]={});var m=s[String(pid)]||(s[String(pid)]={});if(value) m[field]=value; else delete m[field];if(!deferSave) wrSave();}
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
      if(js.length) unique.push(playerRef(m)+" — only favorable direct option vs "+js.map(function(j){return w.blocks[j].opponent_label+" ("+wrSaveRecord(w.matrix[i].cells[j])+")";}).join(", "));
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
      threats:wrLiveThreats(w,rem).filter(function(c){return unplayed[c.j];}),
      concerning:w.concerning.filter(function(c){return rem[String(c.our.id)]&&unplayed[c.j];}),
      metrics:[
        ["Remaining players",!n?"—":remN+" of "+n+(unk>0?" ("+unk+" with unknown availability — still counted as remaining)":"")],
        ["Remaining skill total",!n?"—":(remMiss===0?remSL+" (all remaining players have a captured SL)":remSL+" known subtotal · "+remMiss+" remaining player(s) without a captured SL — not a complete total")],
        ["Selected lineup (Planned + Played)",selN===0?"No players marked Planned or Played yet.":(selMiss===0?"Skill total "+selSL+" for "+selN+" selected player(s)":"Known subtotal "+selSL+" · "+selMiss+" selected player(s) without a captured SL")+(cap?" · your reference cap: "+cap+" (user-entered, not verified)":"")+" — not a lineup-legality check."],
        ["Roster flexibility",openN===0?"—":"Favorable direct option left vs "+greenOpps+" of "+openN+" unplayed opponents · any evidence-backed option vs "+sendOpps+" of "+openN]
      ]};
  }

  // ---- Send lists outside Tonight (mirrors analytics send_labels / send_list_text / best_send_text) ----
  function wrGroupKey(r){return String(r.rank).replace("=","");}
  function wrSendLabels(rows){
    var order={},count={},n=0;
    rows.forEach(function(r){if(r.category!=="G"&&r.category!=="E") return;var k=wrGroupKey(r);if(!(k in order)) order[k]=++n;count[k]=(count[k]||0)+1;});
    return rows.map(function(r){if(r.category!=="G"&&r.category!=="E") return "≈";var k=wrGroupKey(r);return order[k]+(count[k]>1?"=":".");});
  }
  function wrSendRecord(r){return r.c.direct?wlText(r.c.direct.w,r.c.direct.g)+" ("+plural(r.c.direct.g,"meeting")+")"+(r.c.direct.g<3?" · SMALL SAMPLE":""):r.cell;}
  function wrSendListText(rows,limit){var l=wrSendLabels(rows);return rows.slice(0,limit||3).map(function(r,i){return l[i]+" "+r.player+" — "+wrSendRecord(r);}).join(" · ");}
  function wrBestSendText(rows){
    if(!rows.length) return "";
    var f=rows[0],tag;
    if(f.category==="I"){var n=rows.filter(function(r){return r.category==="I";}).length;tag="shared-opponent candidate, not ordered ("+(n===1?"the only one":"one of "+n)+"): ";}
    else{var t=rows.filter(function(r){return (r.category==="G"||r.category==="E")&&wrGroupKey(r)===wrGroupKey(f);}).length;
      tag=t===1?"direct-record order #1: ":"direct-record order #1 (tied with "+(t-1)+" other"+(t>2?"s":"")+", same evidence): ";}
    return tag+f.player+" — reason: "+f.reason;
  }
  window.__ucSendTexts=function(ourKey,oppKey,fmt,remainingIds){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt),rem={};
    w.ours.forEach(function(m){rem[String(m.id)]=!remainingIds||remainingIds.map(String).indexOf(String(m.id))>=0;});
    return w.blocks.map(function(b){var rows=b.rows.filter(function(r){return WR_SENDABLE[r.category]&&rem[String(r.member.id)];});return [wrSendListText(rows),wrBestSendText(rows)];});
  };

  // ---- Next Send (mirrors analytics.ultimate_coach_war_room.next_send / next_send_lines) ----
  // Every ORDERED direct candidate (favorable, then even) gets its own numbered line, in ranking
  // order -- nothing hidden behind a "+N more" collapse (SEND-LAYOUT-01); same evidence = same
  // rank, named as tied, and the first three ranks also carry a medal. Shared-opponent-only
  // candidates are one unordered "≈" group; concerning records are "Avoid" (worst first); no
  // evidence is unknown, never weak. Names shown here omit the APA record ID (NAME-DISPLAY-01),
  // via wrDisplayName; nothing is re-scored or weighted.
  var WR_MEDALS=["🥇","🥈","🥉"];
  // Captain-facing name with no APA record ID. Every lookup still keys on member.id. Duplicate
  // names on the roster are told apart by a differing captured skill level, or else a readable
  // position among the duplicates -- never the raw record ID.
  function wrDisplayName(member,roster){
    var dupes=roster.filter(function(m){return m.id!==member.id&&String(m.name||"").trim().toLowerCase()===String(member.name||"").trim().toLowerCase();});
    if(dupes.length&&wrKnown(member.skill_level)&&!dupes.some(function(m){return m.skill_level===member.skill_level;}))
      return member.name+" (SL "+member.skill_level+")";
    return playerRef(member);
  }
  function wrSaveRecord(r){var d=r.c.direct;return d?wlText(d.w,d.g)+" in "+plural(d.g,"meeting")+(d.g<3?", small sample":"")+(d.g===1?" · Only 1 meeting":""):"";}
  function wrNextSend(w,j,rem,unplayed){
    var b=w.blocks[j],roster=w.ours;
    if(!unplayed[j]) return {opponent:b.opponent,label:b.opponent_label,headline:b.opponent.name+" has already played.",ranked:[],unordered:[],avoid:[],unknown:[]};
    var rows=b.rows.filter(function(r){return rem[String(r.member.id)];});
    var onlyGreen={};
    w.blocks.forEach(function(o,k){if(k===j||!unplayed[k]) return;
      var g=o.rows.filter(function(r){return r.category==="G"&&rem[String(r.member.id)];});
      if(g.length===1){var id=String(g[0].member.id);(onlyGreen[id]||(onlyGreen[id]=[])).push({opponent:o.opponent,
        label:wrDisplayName(o.opponent,w.theirs)+" ("+wrSaveRecord(g[0])+")"});}});
    var saveText=function(targets){return targets?"consider saving — our only favorable direct option vs "+targets.map(function(t){return t.label;}).join(", "):"";};
    var groups=[];
    rows.forEach(function(r){if(r.category!=="G"&&r.category!=="E") return;var last=groups[groups.length-1];
      if(last&&String(last[0].rank).replace("=","")===String(r.rank).replace("=","")) last.push(r); else groups.push([r]);});
    var ranked=[];
    groups.forEach(function(group,g){
      var medal=g<WR_MEDALS.length?WR_MEDALS[g]:"";
      group.forEach(function(r){var save=onlyGreen[String(r.member.id)];
        ranked.push({rank:r.rank,choice_number:g+1,medal:medal,member:r.member,display:wrDisplayName(r.member,roster),category:r.category,reason:r.reason,
          tied_with:group.filter(function(o){return o!==r;}).map(function(o){return wrDisplayName(o.member,roster);}),
          save:saveText(save),save_targets:save||[]});});
    });
    var pick=function(cat){return function(r){return r.category===cat;};},brief=function(r){var sv=onlyGreen[String(r.member.id)];
      return {member:r.member,display:wrDisplayName(r.member,roster),reason:r.reason,
              save:saveText(sv),save_targets:sv||[]};};
    var unordered=rows.filter(pick("I")).map(brief),avoid=rows.filter(pick("R")).map(brief);
    var unknown=rows.filter(pick("X")).map(function(r){return wrDisplayName(r.member,roster);});
    var headline=ranked.length?"Direct-record order #1: "+ranked[0].display+(ranked[0].tied_with.length?" or "+ranked[0].tied_with.join(", ")+" (tied)":"")
      :unordered.length?"No favorable/even direct option — shared-opponent candidates only (≈, not ordered)"
      :"No evidence-backed option left among our remaining players";
    return {opponent:b.opponent,label:b.opponent_label,headline:headline,ranked:ranked,unordered:unordered,avoid:avoid,unknown:unknown};
  }
  var WR_DIRECT_ORDER_NOTE='Order uses recorded win percentage before meeting count, not confidence. A 1-0 record can appear before 8-2; compare sample sizes.';
  function wrSaveWarning(candidate,w,spending){
    if(!candidate.save_targets.length) return "";
    return ' <span class="ns-save">'+(spending?'· Sending now spends our only favorable direct option vs ':'· consider saving — our only favorable direct option vs ')
      +candidate.save_targets.map(function(t){var row=null;
        w.blocks.forEach(function(b){if(b.opponent.id===t.opponent.id) row=b.byMember[String(candidate.member.id)];});
        var single=row&&row.c.direct&&row.c.direct.g===1;
        return '<button type="button" class="ns-save-target" data-inspect-our="'+esc(candidate.member.id)
        +'" data-inspect-opp="'+esc(t.opponent.id)+'" aria-label="View meetings: '+esc(candidate.display)+' vs '+esc(t.label)+'">'
        +esc(t.label.replace(" · Only 1 meeting",""))+(single?' <strong class="ns-sample">⚠ Only 1 meeting</strong>':'')+' — view meetings</button>';}).join(", ")+'</span>';
  }
  function wrNextSendLines(ns){
    var lines=[ns.headline];
    if(ns.ranked.length) lines.push(WR_DIRECT_ORDER_NOTE);
    ns.ranked.forEach(function(m){var prefix=m.choice_number+".";
      lines.push(prefix+" "+m.display+" — "+m.reason+(m.tied_with.length?" · tied with "+m.tied_with.join(", "):"")+(m.save?" · "+m.save:""));});
    ns.unordered.forEach(function(u){lines.push("≈ "+u.display+" — "+u.reason+(u.save?" · "+u.save:""));});
    ns.avoid.forEach(function(a){lines.push("⚠ Avoid "+a.display+" — "+a.reason);});
    ns.unknown.forEach(function(name){lines.push("❓ Unknown (no verified evidence, not weak): "+name);});
    return lines;
  }
  window.__ucNextSend=function(ourKey,oppKey,fmt,j,remainingIds,unplayed){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt),rem={};
    w.ours.forEach(function(m){rem[String(m.id)]=!remainingIds||remainingIds.map(String).indexOf(String(m.id))>=0;});
    return wrNextSendLines(wrNextSend(w,j,rem,unplayed||w.theirs.map(function(){return true;})));
  };
  // ---- Match Night Engine (M3): mirrors analytics/match_night_engine.py exactly (same order, same tie-breaks) ----
  var MN_LEVEL_ORDER=["Strong","Solid","Thin","Unknown","Conflicted","Caution"];
  function mnKnown(sl){return typeof sl==="number"&&isFinite(sl)&&sl>0;}
  function mnBits(m){var n=0;while(m){n+=m&1;m>>>=1;}return n;}
  function MnNight(ours,theirs,value,gamesLeft,cap,used,oppCap,oppUsed){
    this.ours=ours;this.theirs=theirs;this.value=value;this.gamesLeft=gamesLeft;this.cap=cap;this.used=used;
    this.oppCap=(oppCap===undefined)?null:oppCap;this.oppUsed=oppUsed||0;this.theirMemo={};
    this.fullOurs=(1<<ours.length)-1;this.fullTheirs=(1<<theirs.length)-1;this.memo={};this.legalMemo={};
  }
  MnNight.prototype.spent=function(om){var s=0,self=this;this.ours.forEach(function(p,i){if(!(om>>i&1)&&mnKnown(p.sl)) s+=Math.trunc(p.sl);});return s;};
  MnNight.prototype.legal=function(om,i,gamesAfter){
    if(this.cap===null) return true;
    var key=om+"|"+i;
    if(!(key in this.legalMemo)) this.legalMemo[key]=this.legalNow(om,i,gamesAfter);
    return this.legalMemo[key];
  };
  MnNight.prototype.legalNow=function(om,i,gamesAfter){
    var rest=[],unknown=0;
    this.ours.forEach(function(p,k){if((om>>k&1)&&k!==i){if(mnKnown(p.sl)) rest.push(Math.trunc(p.sl)); else unknown++;}});
    rest.sort(function(a,b){return a-b;});
    var need=Math.max(0,gamesAfter-unknown);if(need>rest.length) need=rest.length;
    var sum=0;for(var k=0;k<need;k++) sum+=rest[k];
    var own=mnKnown(this.ours[i].sl)?Math.trunc(this.ours[i].sl):0;
    return this.used+this.spent(om)+own+sum<=this.cap;
  };
  MnNight.prototype.theirLegal=function(om,tm,j){
    if(this.oppCap===null) return true;
    var after=this.gamesRemaining(om)-1,key=tm+"|"+j+"|"+after;
    if(key in this.theirMemo) return this.theirMemo[key];
    var spent=0,rest=[],unknown=0;
    this.theirs.forEach(function(p,k){
      if(!(tm>>k&1)){if(mnKnown(p.sl)) spent+=Math.trunc(p.sl);return;}
      if(k===j) return;
      if(mnKnown(p.sl)) rest.push(Math.trunc(p.sl)); else unknown++;
    });
    rest.sort(function(a,b){return a-b;});
    var need=Math.min(Math.max(0,after-unknown),rest.length),sum=0;for(var q=0;q<need;q++) sum+=rest[q];
    var own=mnKnown(this.theirs[j].sl)?Math.trunc(this.theirs[j].sl):0;
    return (this.theirMemo[key]=this.oppUsed+spent+own+sum<=this.oppCap);
  };
  MnNight.prototype.legalTheirs=function(om,tm){
    var out=[];if(this.gamesRemaining(om)<=0) return out;
    for(var j=0;j<this.theirs.length;j++) if((tm>>j&1)&&this.theirLegal(om,tm,j)) out.push(j);
    return out;
  };
  MnNight.prototype.gamesRemaining=function(om){return this.gamesLeft-(mnBits(this.fullOurs)-mnBits(om));};
  MnNight.prototype.pair=function(i,j){return this.value[String(this.ours[i].id)+"|"+String(this.theirs[j].id)].points;};
  MnNight.prototype.legalOurs=function(om){
    var g=this.gamesRemaining(om),out=[];if(g<=0) return out;
    for(var i=0;i<this.ours.length;i++) if((om>>i&1)&&this.legal(om,i,g-1)) out.push(i);
    return out;
  };
  MnNight.prototype.solve=function(om,tm,weLead){
    var key=om+"|"+tm+"|"+(weLead?1:0);
    if(key in this.memo) return this.memo[key];
    var ours=this.legalOurs(om),theirs=this.legalTheirs(om,tm),j,i,v,best=null;
    if(!ours.length||!theirs.length){this.memo[key]=0;return 0;}
    if(weLead){
      for(var a=0;a<ours.length;a++){i=ours[a];var worst=null;
        for(var b=0;b<theirs.length;b++){j=theirs[b];v=this.pair(i,j)+this.solve(om&~(1<<i),tm&~(1<<j),false);if(worst===null||v<worst) worst=v;}
        if(best===null||worst>best) best=worst;}
    }else{
      for(var c=0;c<theirs.length;c++){j=theirs[c];var top=null;
        for(var d=0;d<ours.length;d++){i=ours[d];v=this.pair(i,j)+this.solve(om&~(1<<i),tm&~(1<<j),true);if(top===null||v>top) top=v;}
        if(best===null||top<best) best=top;}
    }
    this.memo[key]=best;return best;
  };
  MnNight.prototype.bestAnswer=function(om,tm,j){
    var bi=null,bv=null,L=this.legalOurs(om);
    for(var a=0;a<L.length;a++){var i=L[a],v=this.pair(i,j)+this.solve(om&~(1<<i),tm&~(1<<j),true);if(bv===null||v>bv){bi=i;bv=v;}}
    return [bi,bv===null?0:bv];
  };
  MnNight.prototype.lead=function(om,tm){
    var best=[null,null,null],L=this.legalOurs(om);
    for(var a=0;a<L.length;a++){var i=L[a],reply=null,worst=null,T=this.legalTheirs(om,tm);
      for(var b=0;b<T.length;b++){var j=T[b];
        var v=this.pair(i,j)+this.solve(om&~(1<<i),tm&~(1<<j),false);if(worst===null||v<worst){reply=j;worst=v;}}
      if(reply!==null&&(best[2]===null||worst>best[2])) best=[i,reply,worst];}
    return [best[0],best[1],best[2]===null?0:best[2]];
  };
  MnNight.prototype.principalLine=function(om,tm,weLead){
    var line=[];
    while(this.gamesRemaining(om)>0&&this.legalOurs(om).length&&this.legalTheirs(om,tm).length){
      var i,j;
      if(weLead){var l=this.lead(om,tm);i=l[0];j=l[1];}
      else{var worst=null;j=null;
        var T2=this.legalTheirs(om,tm);for(var t2=0;t2<T2.length;t2++){var jj=T2[t2],v=this.bestAnswer(om,tm,jj)[1];if(worst===null||v<worst){j=jj;worst=v;}}
        i=this.bestAnswer(om,tm,j)[0];}
      if(i===null||j===null) break;
      line.push({leader:weLead?"us":"them",our:i,their:j});
      om&=~(1<<i);tm&=~(1<<j);weLead=!weLead;
    }
    return line;
  };
  function mnKeyGreater(a,b){return b===null||a[0]>b[0]||(a[0]===b[0]&&a[1]>b[1]);}
  // Exact best board by dynamic programming over their players (mirrors _best_board: same option order,
  // only a strictly better (total, worst pairing) replaces the current choice).
  function mnBestBoard(night,k,floor){
    var no=night.ours.length,nt=night.theirs.length,memo={},BIG=1000000000;
    function theirSl(j){return mnKnown(night.theirs[j].sl)?Math.trunc(night.theirs[j].sl):0;}
    function capOk(mask){
      if(night.cap===null) return true;
      var s=0;night.ours.forEach(function(p,i){if((mask>>i&1)&&mnKnown(p.sl)) s+=Math.trunc(p.sl);});
      return night.used+s<=night.cap;
    }
    function f(j,mask,tsum){
      var count=mnBits(mask);
      if(night.oppCap!==null&&night.oppUsed+tsum>night.oppCap) return null;
      if(count===k) return capOk(mask)?[[0,BIG],[]]:null;
      if(j===nt||nt-j<k-count) return null;
      var key=j+"|"+mask+"|"+tsum;if(key in memo) return memo[key];
      var best=null;
      for(var i=0;i<no;i++){
        if(mask>>i&1) continue;
        var v=night.pair(i,j);if(floor!==null&&v<floor) continue;
        var rest=f(j+1,mask|(1<<i),tsum+theirSl(j));if(rest===null) continue;
        var cand=[[v+rest[0][0],Math.min(v,rest[0][1])],[[i,j]].concat(rest[1])];
        if(best===null||mnKeyGreater(cand[0],best[0])) best=cand;
      }
      var skip=f(j+1,mask,tsum);
      if(skip!==null&&(best===null||mnKeyGreater(skip[0],best[0]))) best=skip;
      memo[key]=best;return best;
    }
    return f(0,0,0);
  }
  function mnBoard(night,k,safest){
    if(!safest){var found=mnBestBoard(night,k,null);return found?found[1]:[];}
    var seen={},values=[];
    for(var i=0;i<night.ours.length;i++) for(var j=0;j<night.theirs.length;j++){var v=night.pair(i,j);if(!seen[v]){seen[v]=1;values.push(v);}}
    values.sort(function(a,b){return b-a;});
    for(var n=0;n<values.length;n++){var f2=mnBestBoard(night,k,values[n]);if(f2) return f2[1];}
    return [];
  }
  function mnCapSafety(night,om){
    if(night.cap===null) return null;
    var known=[],unknown=0;night.ours.forEach(function(p,i){if(om>>i&1){if(mnKnown(p.sl)) known.push(Math.trunc(p.sl)); else unknown++;}});
    known.sort(function(a,b){return a-b;});var need=Math.min(night.gamesLeft,known.length),cheapest=0;for(var k=0;k<need;k++) cheapest+=known[k];
    return {cap:night.cap,used:night.used,cheapest_rest:cheapest,slack:night.cap-night.used-cheapest,incomplete:unknown>0};
  }
  function mnMatchPlan(ours,theirs,value,gamesLeft,cap,used,oppCap,oppUsed){
    cap=(cap===undefined)?null:cap;used=used||0;oppCap=(oppCap===undefined)?null:oppCap;oppUsed=oppUsed||0;
    gamesLeft=Math.max(0,Math.min(gamesLeft,ours.length,theirs.length));
    var night=new MnNight(ours,theirs,value,gamesLeft,cap,used,oppCap,oppUsed),om=night.fullOurs,tm=night.fullTheirs;
    if(oppCap!==null&&gamesLeft&&!night.legalTheirs(om,tm).length){night=new MnNight(ours,theirs,value,gamesLeft,cap,used);oppCap=null;}
    function name(side,i){return (side==="our"?night.ours:night.theirs)[i].name;}
    function conf(i,j){return night.value[String(night.ours[i].id)+"|"+String(night.theirs[j].id)];}
    var incomplete=cap!==null&&ours.some(function(p){return !mnKnown(p.sl);});
    var out={games_left:gamesLeft,cap_incomplete:incomplete,
      opponent_budget:oppCap===null?null:{cap:oppCap,used:oppUsed,incomplete:theirs.some(function(p){return !mnKnown(p.sl);})}};
    if(!gamesLeft||!night.legalOurs(om).length){
      out.lead=null;out.responses=[];out.holds=[];out.sacrifices=[];out.plan_if_we_lead=[];out.plan_if_they_lead=[];
      out.best_board=[];out.safest_board=[];out.confidence={};out.fragility=null;out.cap=mnCapSafety(night,om);return out;
    }
    var l=night.lead(om,tm),li=l[0],lj=l[1],leadValue=l[2],equal=[],LO=night.legalOurs(om);
    var LT=night.legalTheirs(om,tm);
    for(var q=0;q<LO.length;q++){var ii=LO[q];if(ii===li) continue;var ww=null;
      for(var tq=0;tq<LT.length;tq++){var jq=LT[tq],vv=night.pair(ii,jq)+night.solve(om&~(1<<ii),tm&~(1<<jq),false);if(ww===null||vv<ww) ww=vv;}
      if(ww===leadValue) equal.push(name("our",ii));}
    out.lead={our:name("our",li),our_id:ours[li].id,their_reply:name("their",lj),level:conf(li,lj).level,why:conf(li,lj).text,equally_good:equal};
    var totalThey=night.solve(om,tm,false),responses=[];
    for(var rj=0;rj<LT.length;rj++){var j=LT[rj];
      var ba=night.bestAnswer(om,tm,j),i=ba[0],v=ba[1];if(i===null) continue;
      var L=night.legalOurs(om),naive=L[0];for(var a=1;a<L.length;a++) if(night.pair(L[a],j)>night.pair(naive,j)) naive=L[a];
      var cost="";
      if(naive!==i&&night.pair(naive,j)>night.pair(i,j)){
        var later=v-(night.pair(naive,j)+night.solve(om&~(1<<naive),tm&~(1<<j),true));
        cost=later>0?name("our",naive)+" is the stronger answer tonight ("+conf(naive,j).level+"), but sending them now costs more later; keep "+name("our",naive)+" for the rest of the night":"";
      }
      responses.push({their:name("their",j),our:name("our",i),level:conf(i,j).level,why:conf(i,j).text,cost_later:cost});
    }
    out.responses=responses;
    var base=night.solve(om,tm,true),drops=[];
    for(var x=0;x<ours.length;x++){
      if(!(om>>x&1)) continue;
      var sub=new MnNight(ours.filter(function(p,k){return k!==x;}),theirs,value,Math.min(gamesLeft,ours.length-1,theirs.length),cap,used,oppCap,oppUsed);
      drops.push([base-sub.solve(sub.fullOurs,sub.fullTheirs,true),x]);
    }
    var planLead=night.principalLine(om,tm,true),planThem=night.principalLine(om,tm,false);
    function covers(i){
      var good={Strong:1,Solid:1},mine=[];
      for(var tj=0;tj<LT.length;tj++){var j=LT[tj];
        if(!good[conf(i,j).level]) continue;
        var other=false;for(var ok=0;ok<LO.length;ok++){var k=LO[ok];if(k!==i&&good[conf(k,j).level]&&conf(k,j).points>=conf(i,j).points) other=true;}
        if(!other) mine.push(j);
      }
      return mine.sort(function(a,b){return (conf(i,b).points-conf(i,a).points)||(a-b);});
    }
    var holds=[];
    drops.slice().sort(function(a,b){return (b[0]-a[0])||(a[1]-b[1]);}).forEach(function(d){
      var drop=d[0],i=d[1];if(drop<=0||LO.indexOf(i)<0) return;
      var cov=covers(i),why;
      if(cov.length){var j=cov[0];why="our only "+conf(i,j).level+" answer to "+name("their",j)+" — "+conf(i,j).why;}
      else{
        var margin=function(x){var others=[];for(var ok=0;ok<LO.length;ok++){var k=LO[ok];if(k!==i) others.push(conf(k,x).points);}
          return conf(i,x).points-(others.length?Math.max.apply(null,others):conf(i,x).points);};
        var bj=LT[0];for(var tj=1;tj<LT.length;tj++){var jj=LT[tj];if(margin(jj)>margin(bj)) bj=jj;}
        if(margin(bj)>0){var nxt=null;for(var ok2=0;ok2<LO.length;ok2++){var k2=LO[ok2];if(k2===i) continue;var c2=conf(k2,bj);if(nxt===null||c2.points>nxt.points) nxt=c2;}
          why="our best answer to "+name("their",bj)+" ("+conf(i,bj).level+"); without them the next best is "+nxt.level;}
        else why="the plan is weaker without them";}
      holds.push({our:name("our",i),why:why,covers:cov.map(function(j){return name("their",j);})});
    });
    out.holds=holds.filter(function(h){return h.our!==out.lead.our;}).slice(0,3);
    var kept=out.holds.filter(function(h){return h.covers.length;}).map(function(h){return h.our;});
    out.lead.why_lead="Lead "+out.lead.our+": "+(kept.length?"keeps "+kept.join(", ")+" for their best answers; ":"")
      +"their most damaging reply is "+out.lead.their_reply+" ("+out.lead.level+" for us)";
    var dropOf={};drops.forEach(function(d){dropOf[d[1]]=d[0];});
    var weak=planLead.filter(function(p){return conf(p.our,p.their).points<=0;});
    weak.sort(function(a,b){return ((dropOf[a.our]||0)-(dropOf[b.our]||0))||(conf(a.our,a.their).points-conf(b.our,b.their).points)||(a.our-b.our);});
    out.sacrifices=weak.slice(0,2).map(function(p){return {our:name("our",p.our),their:name("their",p.their),level:conf(p.our,p.their).level,
      why:"lowest-cost concession — "+conf(p.our,p.their).text};});
    function describe(line){return line.map(function(p,n){return {game:n+1,leader:p.leader,our:name("our",p.our),their:name("their",p.their),level:conf(p.our,p.their).level};});}
    out.plan_if_we_lead=describe(planLead);out.plan_if_they_lead=describe(planThem);
    function board(pairs){return pairs.map(function(p){return {our:name("our",p[0]),their:name("their",p[1]),level:conf(p[0],p[1]).level};});}
    out.best_board=board(mnBoard(night,gamesLeft,false));out.safest_board=board(mnBoard(night,gamesLeft,true));
    var counts={};MN_LEVEL_ORDER.forEach(function(lv){counts[lv]=0;});planLead.forEach(function(p){counts[conf(p.our,p.their).level]++;});
    out.confidence={};MN_LEVEL_ORDER.forEach(function(lv){if(counts[lv]) out.confidence[lv]=counts[lv];});
    var wd=0,wi=null;drops.forEach(function(d){if(wi===null||d[0]>wd||(d[0]===wd&&d[1]<wi)){wd=d[0];wi=d[1];}});
    if(!drops.length){wd=0;wi=null;}
    var thin=planLead.filter(function(p){var lv=conf(p.our,p.their).level;return lv==="Thin"||lv==="Conflicted";});
    out.fragility={player:wd>0?name("our",wi):null,player_drop:wd,
      thin_pairings:thin.map(function(p){return name("our",p.our)+" vs "+name("their",p.their)+" ("+conf(p.our,p.their).level+")";}),
      rating:(wd>=6||thin.length>=2)?"High":(wd>=3||thin.length)?"Medium":"Low"};
    out.cap=mnCapSafety(night,om);out.total_if_we_lead=base;out.total_if_they_lead=totalThey;
    return out;
  }
  // The plan for this War Room as it stands (mirrors analytics.match_night_engine.plan_for_war_room).
  function mnPlanFor(w,rem,unplayed,playedCount,playedSl,cap){
    var ours=w.ours.filter(function(m){return rem[String(m.id)];}).map(function(m){return {id:m.id,name:wrDisplayName(m,w.ours),sl:m.skill_level===undefined?null:m.skill_level};});
    var theirs=[],value={},oppUsed=0;
    w.blocks.forEach(function(b,j){if(!unplayed[j]&&mnKnown(b.opponent.skill_level)) oppUsed+=Math.trunc(b.opponent.skill_level);});
    w.blocks.forEach(function(b,j){
      if(!unplayed[j]) return;
      theirs.push({id:b.opponent.id,name:wrDisplayName(b.opponent,w.theirs),sl:b.opponent.skill_level===undefined?null:b.opponent.skill_level});
      b.rows.forEach(function(r){value[String(r.member.id)+"|"+String(b.opponent.id)]=r.confidence;});
    });
    return mnMatchPlan(ours,theirs,value,5-playedCount,cap,playedSl,cap,oppUsed);
  }
  window.__ucPlanFor=function(ourKey,oppKey,fmt,remainingIds,unplayed,playedCount,playedSl,cap){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt),rem={};
    w.ours.forEach(function(m){rem[String(m.id)]=!remainingIds||remainingIds.map(String).indexOf(String(m.id))>=0;});
    return mnPlanFor(w,rem,unplayed||w.theirs.map(function(){return true;}),playedCount||0,playedSl||0,cap===undefined?null:cap);
  };
  // Test hook: the engine on explicit inputs (cross-checked with analytics.match_night_engine.match_plan).
  window.__ucMatchPlan=function(ours,theirs,value,gamesLeft,cap,used,oppCap,oppUsed){return mnMatchPlan(ours,theirs,value,gamesLeft,cap,used,oppCap,oppUsed);};
  // Test hook: every pairing's confidence text, [opponent][our player] in roster order (cross-checked with Python).
  window.__ucConfidence=function(ourKey,oppKey,fmt){
    var w=warRoomPair(TEAM_INDEX[ourKey],TEAM_INDEX[oppKey],fmt);
    return w.blocks.map(function(b){return w.ours.map(function(m){return b.byMember[String(m.id)].confidence.text;});});
  };
  // ---- Blind send: WE lead and have not seen their player (mirrors analytics.blind_send) ----
  // Every other recommendation here answers "they put up X, who answers?". In APA the lead
  // alternates, so a captain regularly chooses first. Worst case first (maximin), coverage
  // second; nothing predicts their lineup and no record means unknown, never weak.
  function wrBlindSend(w,plan){
    var live=[],i;
    for(i=0;i<w.blocks.length;i++) if(plan.unplayed[i]) live.push(w.blocks[i]);
    if(!live.length) return null;
    var stats={},order=0,any=false;
    w.ours.forEach(function(m){ if(plan.rem[String(m.id)]){ stats[m.id]={member:m,order:order++,concerning:0,favorable:0,even:0}; any=true; } });
    if(!any) return null;
    live.forEach(function(b){ b.rows.forEach(function(r){
      var st=stats[r.member.id]; if(!st) return;
      if(r.category==="R") st.concerning++; else if(r.category==="G") st.favorable++; else if(r.category==="E") st.even++;
    });});
    var ranked=Object.keys(stats).map(function(k){return stats[k];});
    ranked.forEach(function(x){x.coverage=x.concerning+x.favorable+x.even;x.gap=live.length-x.coverage;});
    ranked.sort(function(a,b){
      return a.concerning-b.concerning || b.favorable-a.favorable || b.even-a.even || a.order-b.order;});
    var n=live.length,t=ranked[0];
    // If the leading candidate holds no direct record at all he is not a recommendation -- he just
    // sorted above players with a LOSING record. Unknown is not evidence of a safer lead and must
    // never be printed as one ("even vs 0 of 2" was that bug). Name nobody and show the tradeoff.
    // Kept short: this sits above the fold on a phone (BLIND-01).
    if(!t.coverage){
      var known=ranked.filter(function(x){return x.coverage>0;}).length,
          bad=ranked.filter(function(x){return x.concerning>0;}).length;
      return {member:null,unranked:true,weak:true,
        why:known?("no record either way for our best-placed option — unknown, not safer"
                   +(bad?" · "+bad+" of your remaining have a concerning record":"")
                   +" · unranked, your read decides")
                : ("nothing recorded either way vs any of "+n+" — your read decides")};
    }
    var gap=t.gap?" · no direct record vs "+t.gap:"",why;
    if(t.concerning) why=t.favorable===0
        ? t.concerning+" concerning of "+n+" — best available, not good"+gap
        : t.favorable+" favorable, "+t.concerning+" concerning of "+n+gap;
    else if(t.favorable) why="favorable vs "+t.favorable+" of "+n+gap;
    else why="even vs "+t.even+" of "+n+gap;
    var ties=ranked.filter(function(x){return x.concerning===t.concerning&&x.favorable===t.favorable&&x.even===t.even;})
      .map(function(x){return x.member;});
    return {member:t.member,why:why,ties:ties,unranked:false,weak:t.favorable===0&&t.even===0};
  }

  // ---- Lineup budget (mirrors analytics.lineup_budget) ----
  // Optional reference comparison: one slot per unplayed roster opponent. Required match sends
  // and format constraints are not configured here, so this cannot establish match legality.
  // No cap is assumed; missing captured SL makes the comparison incomplete.
  function wrLineupBudget(w,plan,ta,sending){
    var cap=parseInt(WR_PLAN.cap[ta.key],10);
    if(!(cap>0)) return null;
    var used=0,unknown=0,pool=[],slots=0,i;
    for(i=0;i<w.blocks.length;i++) if(plan.unplayed[i]) slots++;
    w.ours.forEach(function(m){
      var sl=wrKnown(m.skill_level)?Number(m.skill_level):null;
      if(wrLineup(plan.ck,m.id)==="Played"){ if(sl!==null) used+=sl; else unknown++; return; }
      if(!plan.rem[String(m.id)]) return;
      if(sl===null) unknown++; else pool.push(sl);
    });
    pool.sort(function(a,b){return a-b;});
    var left=cap-used,need=pool.length>=slots?pool.slice(0,slots).reduce(function(a,b){return a+b;},0):null;
    var out={cap:cap,used:used,left:left,slots:slots,unknown:unknown,
             feasible:need===null?null:need<=left,cheapest:need,sendingKeepsLegal:null};
    if(sending!=null){
      var sm=null;w.ours.forEach(function(m){if(String(m.id)===String(sending)) sm=m;});
      if(sm&&wrKnown(sm.skill_level)){
        var rest=[];w.ours.forEach(function(m){
          if(String(m.id)===String(sending)||!plan.rem[String(m.id)]||wrLineup(plan.ck,m.id)==="Played") return;
          if(wrKnown(m.skill_level)) rest.push(Number(m.skill_level));});
        rest.sort(function(a,b){return a-b;});
        var k=Math.max(0,slots-1),after=rest.length>=k?rest.slice(0,k).reduce(function(a,b){return a+b;},0):null;
        if(after!==null) out.sendingKeepsLegal=(Number(sm.skill_level)+after+used)<=cap;
      }
    }
    return out;
  }

  function wrBudgetLine(w,plan,ta,sending){
    var b=wrLineupBudget(w,plan,ta,sending);
    if(!b||!b.slots) return "";
    var bits=["Reference: "+b.slots+" unplayed roster opponents, not verified required sends — not a match-legality check"],cls="ok";
    if(b.unknown){bits.push("Budget check incomplete — "+b.unknown+" without a captured SL; no lineup cleared");}
    else if(b.feasible===false){cls="bad";bits.push("Captured-SL comparison exceeds entered budget: the cheapest "+b.slots+" left total "+b.cheapest+", "+(b.cheapest-b.left)+" over your remaining "+b.left);}
    else if(b.feasible===null) bits.push(b.left+" left for "+b.slots+" more — not enough captured skill levels to check");
    else bits.push(b.left+" of "+b.cap+" left for "+b.slots+" more (cheapest "+b.cheapest+")");
    return '<div class="lineup-budget '+cls+'"><span class="lb-label">Reference budget '+b.cap+' (yours)</span><span>'+esc(bits.join(" · "))+'</span></div>';
  }

  function wrBlindSendCard(w,plan,ta){
    var b=wrBlindSend(w,plan);
    if(!b) return "";
    if(b.unranked)
      return '<div class="blind-send weak"><span class="bs-label">If we put up first</span>'
        +'<b class="bs-name">No evidence-backed pick</b>'
        +'<span class="bs-why">'+esc(b.why)+'</span></div>'+wrBudgetLine(w,plan,ta,null);
    // Unknown availability is said AT the decision, not only in the response card below.
    var av=wrAvail(plan.ck,b.member.id)==="Unknown"?' <span class="ns-avail">· availability unknown</span>':'';
    // Show the meetings behind the existing pairing-count choice; never rescore it.
    var meetings=0,pairings=0,small=0;
    w.blocks.forEach(function(block,j){if(!plan.unplayed[j]) return;
      block.rows.forEach(function(r){if(r.member.id!==b.member.id||!r.c.direct) return;
        meetings+=r.c.direct.g;pairings++;if(r.c.direct.g<3) small++;});});
    return '<div class="blind-send'+(b.weak?" weak":"")+'">'
      +'<span class="bs-label">If we put up first</span>'
      +'<b class="bs-name">'+esc(wrDisplayName(b.member,w.ours))+'</b>'+wrCandidateBudget(w,plan,ta,b.member)
      +'<span class="bs-why">'+esc(b.why)+av+'</span>'
      +'<span class="bs-evidence"><strong>'+esc(plural(meetings,"direct meeting")+" total across "+plural(pairings,"opponent")
        +(small?" · "+plural(small,"small-sample pairing"):""))+'</strong><br>Pairing counts select the first shown, not meeting totals or confidence. Opponents without a direct record remain unknown.</span>'
      +(b.ties.length>1?'<details class="bs-ties"><summary>'+b.ties.length+' tied by matchup counts</summary>'
        +'<p>Same counts of concerning, favorable and even direct pairings. First shown follows roster order. Individual records and meeting totals can differ.</p><ul>'
        +b.ties.map(function(m){return '<li><b>'+esc(wrDisplayName(m,w.ours))+'</b>'
          +(wrAvail(plan.ck,m.id)==="Unknown"?' <span class="ns-avail">· availability unknown</span>':"")+'</li>';}).join("")+'</ul>'
        +'<a href="#wr-matrix">Compare records in Captain Matrix</a></details>':"")+'</div>'
      +wrBudgetLine(w,plan,ta,b.member.id);
  }

  // ---- Dangerous opponents, against who's actually left tonight (mirrors analytics.live_threats) ----
  // The old flag summed a win/loss record across our WHOLE roster's history with an opponent,
  // including players who are Unavailable or have already Played. GPT audit correction: missing
  // evidence is uncertainty, not safety -- this used to say "no longer a live risk" whenever the
  // roster-wide flag depended on departed players, even when some LIVE evidence also existed and
  // simply was not winning. If any live evidence exists, that IS real evidence of no danger and
  // needs no flag at all; "unknown" is reserved for zero live games, where "only against
  // player(s) not in tonight's remaining lineup" is a true statement rather than an overclaim.
  function wrLiveThreats(w,rem){
    var out=[],remainingCount=w.ours.filter(function(m){return rem[String(m.id)];}).length;
    if(!Object.keys(rem).some(function(k){return rem[k];})) return out;
    w.blocks.forEach(function(b,j){
      var live=b.rows.filter(function(r){return r.c.direct&&rem[String(r.member.id)];});
      var gone=b.rows.filter(function(r){return r.c.direct&&!rem[String(r.member.id)];});
      var lw=0,lg=0;live.forEach(function(r){lw+=r.c.direct.g-r.c.direct.w;lg+=r.c.direct.g;});
      var gw=0,gg=0;gone.forEach(function(r){gw+=r.c.direct.g-r.c.direct.w;gg+=r.c.direct.g;});
      var dangerousLive=lg>0&&lw>lg-lw,unknownOnly=!lg&&gg>0&&gw>gg-gw;
      if(dangerousLive) out.push({j:j,opponent:b.opponent,label:b.opponent_label,live:true,unknown:false,
        wins:lw,games:lg,playersMet:live.length,
        // Full detail for the War Room risk panel, which has room; a compact line for Tonight,
        // which does not -- a longer version of this exact text pushed Open risks off a 390x844
        // Safari screen (the fourth time an addition here has done that).
        text:b.opponent_label+" · SL "+slText(b.opponent)+" · "+wlText(lw,lg)+" vs our roster still in play ("+plural(lg,"meeting")+", "+live.length+" of "+plural(remainingCount,"remaining player")+")"
          +(remainingCount>live.length?" · no direct record vs "+plural(remainingCount-live.length,"remaining player"):"")+(lg<3?" · small sample":""),
        short:wrDisplayName(b.opponent,w.theirs)+" — "+wlText(lw,lg)+(lg<3?" ("+plural(lg,"meeting")+", small sample)":" vs our roster still in play")});
      else if(unknownOnly) out.push({j:j,opponent:b.opponent,label:b.opponent_label,live:false,unknown:true,
        wins:gw,games:gg,playersMet:gone.length,
        text:b.opponent_label+" · SL "+slText(b.opponent)+" · historically "+wlText(gw,gg)+" vs our roster, but that record is only against player(s) not in tonight's remaining lineup — unknown vs who is left, not cleared"+(gg<3?" · small historical sample":""),
        short:wrDisplayName(b.opponent,w.theirs)+" — unknown vs our remaining roster (historically "+wlText(gw,gg)+(gg<3?", small sample":"")+")"});
    });
    out.sort(function(a,b2){
      if(a.unknown!==b2.unknown) return a.unknown?1:-1;
      var ka=a.games?(2*a.wins-a.games):0,kb=b2.games?(2*b2.wins-b2.games):0;
      if(ka!==kb) return kb-ka;
      return memberOrder(a.opponent,b2.opponent);
    });
    return out;
  }

  // ---- What a send costs for the rest of the night (mirrors analytics.send_cost) ----
  // Next Send answers one pairing at a time, so the captain could not see what spending this
  // player leaves him for the opponents still to come. Exact count over records already shown.
  function wrSendCost(w,j,memberId,rem,unplayed){
    var others=[],k;
    for(k=0;k<w.blocks.length;k++) if(k!==j&&unplayed[k]) others.push(w.blocks[k]);
    function covered(skip){
      return others.filter(function(b){
        return b.rows.some(function(r){
          return r.category==="G"&&rem[String(r.member.id)]&&String(r.member.id)!==String(skip);});
      }).map(function(b){return b.opponent;});
    }
    var before=covered(null),still=covered(memberId),
        lost=before.filter(function(o){return !still.some(function(s){return String(s.id)===String(o.id);});}).map(function(o){return wrDisplayName(o,w.theirs);});
    return {others:others.length,before:before.length,after:still.length,lost:lost};
  }

  function wrCostText(w,j,memberId,rem,unplayed){
    var c=wrSendCost(w,j,memberId,rem,unplayed);
    // Only say it when there IS a cost: "leaves 2 of 2" on every candidate is noise, and noise on
    // this card costs height a phone does not have. Silence means nothing is given up.
    // The save flag beside it already NAMES the opponent being given up, so this adds only the
    // size of it -- saying the name twice in one line reads like two different problems (GPT).
    if(!c.others||!c.lost.length) return "";
    return "leaves "+c.after+" of "+c.others+" with a favorable direct option";
  }

  // The Next Send card: chips for every unplayed opponent (the one they put up), then the responses.
  function wrCandidateBudget(w,plan,ta,member){
    var b=wrLineupBudget(w,plan,ta,member.id);
    if(!b||!b.slots) return "";
    var text="",bad=false;
    if(b.sendingKeepsLegal===false){
      bad=true;
      text=b.unknown?"Captured-SL comparison exceeds entered budget; check incomplete":"Reference comparison: this choice exceeds your entered skill budget";
    }
    return text?'<span class="ns-budget'+(bad?' bad':'')+'">'+esc(text)+'</span>':"";
  }

  function wrBudgetScope(w,plan,ta){
    var budget=wrLineupBudget(w,plan,ta,null);
    return budget&&budget.slots&&(budget.unknown||budget.feasible===null)
      ?'<p class="ns-budget-scope muted">Entered skill-budget check incomplete — missing skill levels or remaining players. No choice is cleared; check manually.</p>':"";
  }

  // Update cap-dependent text while typing, without replacing the focused input or action buttons.
  function wrPatchBudget(w,plan,ta){
    var tonight=document.getElementById("tonight"),lab=document.getElementById("lineup-lab");
    if(tonight){
      // The plan depends on the entered cap: re-plan it in place.
      var mp=tonight.querySelector("#match-plan");
      if(mp){var opened=Array.prototype.filter.call(mp.querySelectorAll("details"),function(d){return d.open;}).map(function(d){return d.className;});
        mp.outerHTML=wrMatchPlanCard(w,plan,ta);
        opened.forEach(function(cls){var d=tonight.querySelector("#match-plan details."+cls.split(" ").join("."));if(d) d.open=true;});}
      Array.prototype.forEach.call(tonight.querySelectorAll(".lineup-budget,.ns-budget,.ns-budget-scope"),function(el){el.remove();});
      var card=tonight.querySelector("#match-plan");
      if(card) card.insertAdjacentHTML("afterend",wrBudgetLine(w,plan,ta,mnLeadId(w,plan,ta)));
      var list=tonight.querySelector("#next-send .ns-list");
      if(list) list.insertAdjacentHTML("beforebegin",wrBudgetScope(w,plan,ta));
      Array.prototype.forEach.call(tonight.querySelectorAll("#next-send .ns-medal"),function(row){
        var send=row.querySelector("[data-send-our]"),why=row.querySelector(".ns-why");
        if(!send||!why) return;
        w.ours.forEach(function(m){if(String(m.id)===send.getAttribute("data-send-our")) why.insertAdjacentHTML("beforeend",wrCandidateBudget(w,plan,ta,m));});
      });
    }
    var facts=lab&&lab.querySelector(".matchup-facts");
    if(facts) facts.innerHTML=plan.metrics.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join("");
  }

  function wrBroaderRecords(w,plan,ta,tb,opp){
    var record=function(m){return wrKnown(m.matches_won)&&wrKnown(m.matches_played)?wlText(m.matches_won,m.matches_played):"Not captured";};
    var scope=function(t){return t?t.name+" · "+(t.session_name||"session not captured")+" · "+fmtLabel(w.format):"Roster scope not captured · "+fmtLabel(w.format);};
    return '<section class="ns-broader"><h4>Broader records — Not used in this ordering</h4>'
      +'<p>Captured team/session record — not a lifetime record. These records do not adjust the direct-record order.</p>'
      +'<p><b>Our roster:</b> '+esc(scope(ta))+'</p><ul>'+w.ours.filter(function(m){return plan.rem[String(m.id)];}).map(function(m){var row=w.blocks.filter(function(b){return b.opponent.id===opp.id;})[0].rows.filter(function(r){return r.member.id===m.id;})[0];return '<li>'+esc(wrDisplayName(m,w.ours))+': <b>'+esc(record(m))+'</b>'+(row.c.direct?'':' · no verified direct meetings')+'</li>';}).join("")+'</ul>'
      +'<p><b>Selected opponent:</b> '+esc(scope(tb))+'</p><p>'+esc(wrDisplayName(opp,w.theirs))+': <b>'+esc(record(opp))+'</b></p>'
      +'<p>Meeting age, changes in skill level and Coach Observations do not adjust this order. Availability filters the list; skill-budget warnings are separate reference checks.</p></section>';
  }

  // Evidence-strength presentation only: existing row order and categories are untouched.
  function wrNextSendEvidence(w,plan,ns,sel){
    if(!ns.ranked.length) return "";
    var lead=ns.ranked[0],record=w.blocks[sel].byMember[String(lead.member.id)].c.direct;
    var names=[lead.display].concat(lead.tied_with).join(" / ");
    var head='<div class="ns-evidence-head"><b>Direct-record order #1'+(lead.tied_with.length?' (tied)':'')+'</b><br>'
      +esc(names+" — "+wlText(record.w,record.g)+" direct record · "+plural(record.g,"meeting"))
      +(record.g<3?'<br><strong class="ns-sample">⚠ Small sample</strong>':'')+'</div>';
    var deeper=record.g<3?w.blocks[sel].rows.filter(function(r){return plan.rem[String(r.member.id)]&&r.c.direct&&r.c.direct.g>record.g;}):[];
    return head+(deeper.length?'<div class="ns-deeper"><b>Deeper direct records</b> — more meetings, not a new order<ul>'
      +deeper.map(function(r){return '<li>'+esc(wrDisplayName(r.member,w.ours)+" — "+wlText(r.c.direct.w,r.c.direct.g)+" in "+plural(r.c.direct.g,"meeting")+" · "+WR_CAT_WORD[r.category]+(r.c.direct.g<3?" · ⚠ small sample":""))+'</li>';}).join("")+'</ul></div>':'');
  }

  // The Match Night Plan's answer to the selected opponent, first: the evidence list below is the support.
  function wrPlanAnswer(r,spending){
    if(!r) return "";
    return '<div class="ns-plan-answer"><span class="mp-label">Match Night Plan answer</span><b>'+esc(r.our)+'</b> '
      +'<span class="mp-level mp-'+r.level.toLowerCase()+'">'+esc(r.level)+'</span> <span class="mp-why">'+esc(r.why.split(" — ").slice(1).join(" — "))+'</span>'
      +(r.cost_later?'<span class="mp-cost">'+esc(r.cost_later)+'</span>':'')
      +(spending?'<span class="mp-cost">Future records below show the opportunity spent by this send, not another instruction to hold.</span>':'')
      +'<span class="muted">The list below is the recorded evidence, in direct-record order.</span></div>';
  }
  function wrNextSendCard(w,plan,ta,tb){
    // An explicit put-up belongs to this fixture/format, not the next view of the same roster.
    var selectionScope=plan.ck+"||"+w.format;
    if(WR_STATE.nextScope!==selectionScope){WR_STATE.next=null;WR_STATE.nextScope=selectionScope;}
    var budgetScope=wrBudgetScope(w,plan,ta);
    var open=w.theirs.map(function(o,j){return j;}).filter(function(j){return plan.unplayed[j];});
    if(!open.length) return '<div id="next-send" class="next-send"><h3>Next Send — recorded matchup options</h3><p class="muted">Every opponent has played.</p></div>';
    var sel=open.filter(function(j){return String(w.theirs[j].id)===String(WR_STATE.next);})[0];
    // Nobody has been put up yet: the panel still has to show something, but it must not read as
    // though they HAVE sent this player. Say it is a possibility until the captain taps a chip
    // (BLIND-01 #4).
    var chosen=sel!==undefined;
    if(!chosen) sel=open[0];
    var ns=wrNextSend(w,sel,plan.rem,plan.unplayed),opp=w.theirs[sel];
    var x=mnInputs(w,plan,ta),matchPlan=mnPlanFor(w,plan.rem,plan.unplayed,x.playedN,x.playedSl,x.cap);
    var who=wrDisplayName(opp,w.theirs),answer=(matchPlan.responses||[]).filter(function(r){return r.their===who;})[0];
    var spending=function(candidate){return !!answer&&answer.our===candidate.display;};
    var spends=ns.ranked.concat(ns.unordered).some(function(candidate){return spending(candidate)&&candidate.save_targets.length;});
    // Unknown availability stays eligible (never assumed Unavailable) but is said at the point of decision.
    var avail=function(m){return wrAvail(plan.ck,m.id)==="Unknown"?' <span class="ns-avail">· availability unknown</span>':'';};
    var li=function(cls,html){return '<li class="'+cls+'">'+html+'</li>';};
    return '<div id="next-send" class="next-send" tabindex="-1"><h3>Next Send — options against '+esc(wrDisplayName(opp,w.theirs))+'</h3>'
      +(chosen?'':'<p class="ns-hypothetical">Nobody put up yet — showing a possible response to '
        +esc(wrDisplayName(opp,w.theirs))+'. Tap who they actually put up.</p>')
      +wrPlanAnswer(answer,spends)+wrNextSendEvidence(w,plan,ns,sel)
      +'<div class="ns-chips" role="group" aria-label="Opponent they put up"><span class="ns-ask">'
      +(chosen?'They put up:':'If they put up:')+'</span>'
      +open.map(function(j){var o=w.theirs[j];return '<button type="button" class="ns-chip'+(j===sel?' on':'')+'" data-next="'+esc(o.id)+'" aria-pressed="'+(j===sel)+'">'+esc(wrDisplayName(o,w.theirs)+" · Captured SL "+slText(o))+'</button>';}).join("")+'</div>'
      +'<div class="ns-method"><b>Not an overall player ranking.</b> Direct records are ordered by recorded win percentage before meeting count, not confidence. A 1-0 record can appear before 8-2. <b>First does not mean better supported or the better practical send.</b> Small samples do not reduce position. Equal evidence stays tied. Losing-record cautions use most net losses first, then meeting count.<br>Shared-only comparisons are not ordered. No verified direct/shared comparison means unknown, not weak.</div>'
      +(ns.ranked.length?'':'<p class="ns-head"><b>'+esc(ns.headline)+'</b></p>')+budgetScope+'<ul class="ns-list">'
      +ns.ranked.map(function(m,i){var cost=wrCostText(w,sel,m.member.id,plan.rem,plan.unplayed);
        var evidence=w.blocks[sel].rows.filter(function(r){return r.member.id===m.member.id;})[0].c.direct;
        return li("ns-medal cat-border-"+m.category+(m.save?" ns-with-save":""),'<span class="ns-why"><span class="ns-m">'+esc("Direct-record order "+m.choice_number)+'</span> <b>'+esc(m.display)+'</b> <strong class="ns-sample">'+esc(plural(evidence.g,"meeting")+(evidence.g<3?" · small sample":""))+'</strong> — '+esc(m.reason)
        +(m.tied_with.length?' <span class="muted">· tied with '+esc(m.tied_with.join(", "))+'</span>':'')+wrSaveWarning(m,w,spending(m))+avail(m.member)
        +(cost?'<span class="ns-cost">'+esc(cost)+'</span>':'')+wrCandidateBudget(w,plan,ta,m.member)+'</span>'
        +'<button type="button" class="ns-send secondary" data-send-our="'+esc(m.member.id)+'" data-send-opp="'+esc(opp.id)+'" aria-label="Mark '+esc(m.display)+' sent vs '+esc(wrDisplayName(opp,w.theirs))+'">✓<span class="ns-sent-word"> Sent</span></button>');}).join("")
      +(function(){
        // With a ranked list, the rest folds into one line that still names every player; tap for the reasons.
        var unord=ns.unordered.map(function(u){return li("ns-unordered",'≈ '+esc(u.display)+' — '+esc(u.reason)+' <span class="muted">(not ordered)</span>'+wrSaveWarning(u,w,spending(u))+avail(u.member));}).join("");
        var rest=ns.avoid.map(function(a){var direct=w.blocks[sel].byMember[String(a.member.id)].c.direct;
          return li("ns-avoid",(direct.g===1?'<strong class="ns-sample">Lost once · 1 meeting</strong> Recorded loss: ':'⚠ Avoid record — recorded losses: ')+'<b>'+esc(a.display)+'</b> — '+esc(a.reason));}).join("")
          +ns.unknown.map(function(name){return li("ns-unknown",'❓ Unknown (no verified evidence, not weak): '+esc(name));}).join("");
        if(!ns.ranked.length) return unord+rest+'</ul>';
        if(!unord&&!rest) return '</ul>';
        var sum=[];
        if(ns.avoid.length) sum.push("⚠ Avoid records — recorded losses: "+ns.avoid.map(function(a){var direct=w.blocks[sel].byMember[String(a.member.id)].c.direct;
          return direct.g===1?a.display+" (Lost once · ⚠ Only 1 meeting)":a.display+" ("+a.reason.split(" — ")[0].replace(" direct record","")+(a.reason.indexOf(" · small sample")!==-1?", small sample":"")+")";}).join(", "));
        if(ns.unordered.length) sum.push("≈ "+ns.unordered.length+" not ordered");
        if(ns.unknown.length) sum.push("❓ "+ns.unknown.length+" unknown");
        return '</ul><details class="ns-more"><summary>'+esc(sum.join(" · "))+'</summary><ul class="ns-list">'+unord+rest+'</ul></details>';
      })()
      +wrBroaderRecords(w,plan,ta,tb,opp)
      +wrNoteFlagSlot(opp.id,"preview","your opinion, not APA facts","div","ns-coach")
      +'</div>';
  }

  function wrList(items,empty){return '<ul class="wr-list">'+(items.length?items.map(function(t){return '<li>'+esc(t)+'</li>';}).join(""):'<li class="muted">'+esc(empty)+'</li>')+'</ul>';}
  function wrChip(cat){return '<span class="cat-dot cat-'+cat+'" title="'+esc(WR_CAT_LABELS[cat])+'"></span>';}
  // Open risks on the first screen: a count and the first name, every name one tap away (GPT audit #84: a
  // full roster's name list pushed Risks below a phone screen). Nothing is dropped, only folded.
  function wrRiskSummary(names,unplayedN){
    if(!names.length) return '<span>None — every unplayed opponent still has a favorable direct option</span>';
    if(names.length===1) return '<span>No favorable direct option left vs '+esc(names[0])+'</span>';
    return '<span>No favorable direct option left vs '+names.length+' of '+unplayedN+' unplayed opponents</span>'
      +'<details class="risk-more"><summary>All '+names.length+': '+esc(names.join(", "))+'</summary>'+esc(names.join(", "))+'</details>';
  }
  // ---- Match Night Plan card: the M3 engine for who is left tonight; re-planned on every render ----
  function mnInputs(w,plan,ta){
    var playedN=0,playedSl=0;
    w.ours.forEach(function(m){if(wrLineup(plan.ck,m.id)==="Played"){playedN++;if(wrKnown(m.skill_level)) playedSl+=Number(m.skill_level);}});
    var capRaw=parseInt(WR_PLAN.cap[ta.key],10);
    return {playedN:playedN,playedSl:playedSl,cap:capRaw>0?capRaw:null};
  }
  function mnLeadId(w,plan,ta){var x=mnInputs(w,plan,ta),p=mnPlanFor(w,plan.rem,plan.unplayed,x.playedN,x.playedSl,x.cap);return p.lead?p.lead.our_id:null;}
  function wrMatchPlanCard(w,plan,ta){
    var x=mnInputs(w,plan,ta),p=mnPlanFor(w,plan.rem,plan.unplayed,x.playedN,x.playedSl,x.cap);
    var head='<h3>Match Night Plan</h3>';
    if(!p.lead) return '<div id="match-plan" class="match-plan">'+head+'<p class="muted">'
      +esc(p.games_left?"No legal send fits the entered skill cap — check the cap and remaining skill levels.":"No games left to plan tonight.")+'</p></div>';
    var conf=MN_LEVEL_ORDER.filter(function(lv){return p.confidence[lv];}).map(function(lv){return p.confidence[lv]+" "+lv;}).join(" · ");
    var frag=p.fragility.rating+(p.fragility.player?" — leans most on "+p.fragility.player:"")
      +(p.fragility.thin_pairings.length?" · thin: "+p.fragility.thin_pairings.join(", "):"");
    var capTxt=(p.cap?(p.cap.incomplete?"Cap "+p.cap.cap+": check incomplete (missing skill levels)":"Cap "+p.cap.cap+": "+p.cap.slack+" to spare after the cheapest remaining lineup"):"No skill cap entered")
      +(p.opponent_budget?" · their replies limited to lineups they can field under the same cap":" · assumes any of their players can still be put up");
    var lvl=function(lv){return '<span class="mp-level mp-'+lv.toLowerCase()+'">'+esc(lv)+'</span>';};
    var li=function(html){return '<li>'+html+'</li>';};
    var line=function(rows){return '<ol class="mp-line">'+rows.map(function(g){return li(esc((g.leader==="us"?"We lead: ":"They lead: ")+g.our+" vs "+g.their+" ")+lvl(g.level));}).join("")+'</ol>';};
    var board=function(rows){return '<ul class="mp-board">'+rows.map(function(g){return li(esc(g.our+" → "+g.their+" ")+lvl(g.level));}).join("")+'</ul>';};
    return '<div id="match-plan" class="match-plan">'+head
      +'<p class="mp-sub">'+esc(p.games_left+(p.games_left===1?" game":" games")+" left · Plan: "+(conf||"no pairings")+" · Fragility: "+frag+" · "+capTxt)+'</p>'
      +'<div class="mp-lead"><span class="mp-label">If we put up first</span><b class="mp-name">'+esc(p.lead.our)+'</b> '+lvl(p.lead.level)
        +'<span class="mp-why">'+esc(p.lead.why_lead)+'</span>'
        +(p.lead.equally_good.length?'<details class="mp-ties"><summary>'+esc((p.lead.equally_good.length+1)+" leads hold up equally well")+'</summary><p>'
          +esc("The plan is just as strong leading with "+p.lead.equally_good.join(", ")+". The first is shown by roster order; your read decides.")+'</p></details>':'')
        +'</div>'
      +'<div class="mp-resp"><span class="mp-label">If they put up</span><ul>'+p.responses.map(function(r){
        return li(esc(r.their+" → ")+'<b>'+esc(r.our)+'</b> '+lvl(r.level)+' <span class="mp-why">'+esc(r.why.split(" — ").slice(1).join(" — "))+'</span>'
          +(r.cost_later?'<span class="mp-cost">'+esc(r.cost_later)+'</span>':''));}).join("")+'</ul></div>'
      +(p.holds.length?'<div class="mp-hold"><span class="mp-label">Designated answers</span><ul>'+p.holds.map(function(h){
        var instruction=h.covers.length?'keep for '+h.covers.join(', ')+'; send when that matchup is put up. '+(h.covers.length>1?'One player can cover only one matchup. ':''):'';
        return li('<b>'+esc(h.our)+'</b> — '+esc(instruction+h.why));}).join("")+'</ul></div>':'')
      +(p.sacrifices.length?'<div class="mp-sac"><span class="mp-label">If we must absorb a bad matchup</span><ul>'+p.sacrifices.map(function(s){return li('<b>'+esc(s.our)+'</b> vs '+esc(s.their)+' '+lvl(s.level)+' — '+esc(s.why.split(" — ")[0]));}).join("")+'</ul></div>':'')
      +'<details class="mp-more"><summary>Game plan and boards</summary>'
        +'<p><b>If we win the toss and lead</b></p>'+line(p.plan_if_we_lead)
        +'<p><b>If they lead</b></p>'+line(p.plan_if_they_lead)
        +'<p><b>Best-case board</b> (if every ideal matchup occurs)</p>'+board(p.best_board)
        +'<p><b>Safest board</b> (protects the worst pairing first)</p>'+board(p.safest_board)+'</details>'
      +'<p class="muted mp-foot">Levels describe recorded evidence, not odds. The plan assumes their captain makes the choice that hurts us most, and re-plans after every ✓ Sent.</p></div>';
  }
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
    // One line per unplayed opponent (up to 3): our first-listed remaining option and WHY. A shared-only
    // pick is labelled as one unordered candidate, never "best" (GPT audit #84 P2).
    var sends=[];w.blocks.forEach(function(b,j){
      if(!plan.unplayed[j]||sends.length>=3) return;
      var s=plan.sends[j];
      if(!s.length){sends.push({text:"vs "+wrDisplayName(b.opponent,w.theirs)+": no evidence-backed option left",pid:b.opponent.id});return;}
      var r=s[0],direct=r.category!=="I";
      var tied=direct?s.filter(function(x){return x.category!=="I"&&wrGroupKey(x)===wrGroupKey(r);}):[];
      var tieText=tied.length>1?" (tied with "+(tied.length-1)+" other"+(tied.length>2?"s":"")+"; see Next Send)":"";
      var record=direct?r.cell+" direct"+(r.c.direct.g<3?" ("+plural(r.c.direct.g,"meeting")+", small sample)":"")+tieText
        :(function(n){return n===1?"≈ shared-opponent only (the only shared-opponent candidate)":"≈ shared-opponent only (one of "+n+" unordered candidates)";})(s.filter(function(x){return x.category==="I";}).length);
      sends.push({text:"vs "+wrDisplayName(b.opponent,w.theirs)+": "+wrDisplayName(r.member,w.ours)+" — "+record
        +(direct&&r.sl_context?" · "+r.sl_context:"")+(direct&&r.date_context?" \u00b7 "+r.date_context:""),pid:b.opponent.id});
    });
    var riskNames=w.theirs.filter(function(o,j){return plan.unplayed[j]&&plan.sends[j].filter(function(r){return r.category==="G";}).length===0;})
      .map(function(o){return wrDisplayName(o,w.theirs);});
    el.innerHTML='<h2>Tonight</h2>'
      +(f?'<div class="when">'+esc(f.date_status==="ok"?f.local_display:"Undated fixture")+'</div>':'<div class="when">Teams picked by hand — not a Match Day fixture</div>')
      +'<div class="vs"><b>'+esc(ta.name)+'</b>'+(ctx?' ('+(ctx.ourSide==="home"?"home":"away")+')':'')+' vs <b>'+esc(tb.name)+'</b> · '+esc(fmtLabel(w.format))+(f?' · Venue: '+esc(f.location||"No data"):'')+'</div>'
      +wrMatchPlanCard(w,plan,ta)+wrBudgetLine(w,plan,ta,mnLeadId(w,plan,ta))
      +wrNextSendCard(w,plan,ta,tb)
      +'<div class="tonight-grid decide">'
      +'<div class="decide-sends"><b>Recorded options now</b>'+(sends.length?sends.map(function(x){return '<span>'+esc(x.text)+'</span>'+wrNoteFlagSlot(x.pid,"preview","opinion");}).join(''):'<span>Every opponent has played.</span>')+'</div>'
      +'<div class="decide-threats"><b>Threat records vs remaining roster</b>'+(plan.threats.length?plan.threats.slice(0,3).map(function(t){return '<span'+(t.unknown?' class="unknown"':'')+'>'+(t.live&&t.games===1?'<strong>Beat us once (1 meeting)</strong> — ':'')+esc(t.short)+'</span>'+wrNoteFlagSlot(t.opponent.id,"preview","opinion");}).join(''):'<span>None with a winning recorded record vs us</span>')+(plan.threats.length>3?'<a href="#wr-risks" style="display:inline-flex;align-items:center;min-height:44px">View all '+plan.threats.length+' flagged opponents ('+(plan.threats.length-3)+' more)</a>':'')+'</div>'
      +'<div class="decide-risks"><b>Open risks</b>'+wrRiskSummary(riskNames,unplayedN)+'</div>'
      +'</div><p class="muted ns-foot">Next Send uses recorded results only — not odds. "✓ Sent" marks our player Played and the opponent played (Lineup Lab).</p><div class="tonight-grid detail">'
      +'<div><b>Our team</b><span>Remaining: '+remN+' of '+w.ours.length+'</span><span>Available: '+av.Available+'</span><span>Unavailable: '+av.Unavailable+'</span>'
      +'<span>Unknown: '+av.Unknown+' (not the same as unavailable)</span><span>Already used: '+used+' · planned: '+planned+'</span></div>'
      +'<div><b>Evidence across all pairings</b><span>Favorable direct record (any sample size): '+cat.G+'</span><span>Concerning (more direct losses than wins): '+cat.R+'</span>'
      +'<span>Limited evidence: '+cat.E+' even direct · '+cat.I+' shared-opponent only</span><span>Insufficient verified evidence in this snapshot: '+cat.X+'</span></div>'
      +'<div><b>Opponent roster</b><span>'+w.theirs.length+' players</span><span>Missing information: '+noSL+' player(s) without a captured SL · '+unplayedN+' not yet played</span></div>'
      +'</div><div class="tonight-links"><a href="#team-section">Open the War Room ↓</a><a href="#lineup-lab">Lineup Lab</a><a href="#match-day-card">Change matchup</a></div>';
    // Keep the selected opponent's chip fully visible inside the swipeable row (scrolls the row, not the page).
    var on=el.querySelector("#next-send .ns-chip.on");
    if(on){var row=on.parentNode,left=on.offsetLeft-row.offsetLeft,right=left+on.offsetWidth;
      if(left<row.scrollLeft) row.scrollLeft=left; else if(right>row.scrollLeft+row.clientWidth) row.scrollLeft=right-row.clientWidth;}
  }
  function wrClear(){WR_STATE.next=null;WR_STATE.nextScope=null;var t=document.getElementById("tonight");if(t) t.innerHTML=WR_TONIGHT_NOTE?'<h2>Tonight</h2>'
      +(WR_TONIGHT_NOTE.when?'<div class="when">'+esc(WR_TONIGHT_NOTE.when)+'</div>':'')+'<div class="vs">'+esc(WR_TONIGHT_NOTE.text)+'</div>'
      +'<p class="muted">Following Match Day — nothing to plan until it names one fixture with an opponent roster.</p>'
      +'<div class="tonight-links"><a href="#match-day-card">Change matchup</a></div>':"";["wr-opportunities","wr-risks","wr-matrix","lineup-lab","scouting-cards","wr-meetings"].forEach(function(id){var el=document.getElementById(id);if(el) el.innerHTML="";});}

  function renderWarRoom(ta,tb,fmt){
    var opEl=document.getElementById("wr-opportunities");
    if(!opEl) return;
    if(!ta){wrClear();return;}
    if(!tb||!ta.players.length||!tb.players.length){
      wrClear();
      opEl.innerHTML='<h2>Recorded options</h2><p class="muted">'+(!tb?'No opponent roster for the selected fixture — choose a fixture with a rostered opponent on Match Day, or pick an opponent team above.':'One of these rosters has no current players captured.')+'</p>';
      return;
    }
    var w=warRoomPair(ta,tb,fmt),plan=wrPlan(w,ta,tb);
    wrTonight(w,plan,ta,tb);
    // The detailed ranking is full-roster history, including players no longer in play.
    // Repeat the scope at each matrix-linked entry point, not only above the first table.
    var history=document.getElementById("team-matchups");
    if(history) history.querySelectorAll("h2,.rank-block h3").forEach(function(title){
      if(title.nextElementSibling&&title.nextElementSibling.classList.contains("wr-history-scope")) return;
      var scope=document.createElement("p");scope.className="muted wr-history-scope";
      scope.textContent="Full-roster history, including unavailable and already-played players. These rows ignore tonight's planning marks. ";
      var link=document.createElement("a");link.href="#next-send";link.textContent="Use Next Send for current remaining choices.";
      link.style.cssText="display:inline-flex;align-items:center;min-height:44px";
      scope.appendChild(link);title.insertAdjacentElement("afterend",scope);
    });
    // Best sends (ranking order, sendable + remaining, unplayed opponents)
    opEl.innerHTML='<h2>Recorded options preview per opponent</h2>'
      +'<p class="muted">Favorable direct records first, then even direct (numbered by evidence; "1=" = tied, same evidence), then indirect-only evidence ("≈", not ordered among themselves). Our remaining players only (your Lineup Lab marks). Colors describe recorded results — not odds.</p>'
      +'<p class="muted">'+esc(WR_DIRECT_ORDER_NOTE)+'</p>'
      +'<div class="table-wrap"><table class="send-table"><thead><tr><th>Opponent</th><th>Recorded options among our remaining players</th></tr></thead><tbody>'
      +w.blocks.map(function(b,j){
        var cell=!plan.unplayed[j]?'<span class="muted">Already played.</span>'
          :(plan.sends[j].length?(function(labels){return plan.sends[j].slice(0,3).map(function(r,k){return '<span class="send">'+wrChip(r.category)+esc(labels[k]+" "+r.player+" — "+wrSendRecord(r))+'</span>';}).join('<span class="sep"> · </span>')
            +(plan.sends[j].length>3?'<br><a class="send-more" href="#next-send" style="display:inline-flex;align-items:center;min-height:44px">Showing first 3 of '+plan.sends[j].length+'. Choose '+esc(wrDisplayName(b.opponent,w.theirs))+' in Next Send for all options.</a>':'');})(wrSendLabels(plan.sends[j]))
          :'<span class="muted">No favorable, even or indirect evidence among our remaining players.</span>');
        return '<tr'+(plan.unplayed[j]?'':' class="out"')+'><td>'+esc("vs "+b.opponent_label+" · SL "+slText(b.opponent))+wrNoteFlagSlot(b.opponent.id,"icon")+'</td><td>'+cell+'</td></tr>';
      }).join("")+'</tbody></table></div>';
    document.getElementById("wr-risks").innerHTML='<h2>Top risks</h2><div class="risk-grid">'
      +'<div><h3>Threats — winning direct records</h3><p class="muted">A single win is not an established threat. Live winning records against our remaining players appear first; historical-only flags below are unknown against who is left. Within each group, order follows recorded wins minus losses, not confidence. Unplayed opponents only.</p>'+(function(){
        var items=plan.threats.map(function(c){return '<li>'+(c.live&&c.games===1?'<strong class="ns-sample">Beat us once (1 meeting)</strong> ':'')+esc(c.text)+wrNoteFlagSlot(c.opponent.id,"dot")+'</li>';});
        return '<ul class="wr-list">'+(items.length?items.join(""):'<li class="muted">'+esc("No unplayed opponent has a live winning record against our remaining roster.")+'</li>')+'</ul>';
      })()+'</div>'
      +'<div><h3>Avoid records — more losses than wins</h3><p class="muted">More direct losses than wins (remaining players vs unplayed opponents). A single loss is a caution, not an instruction to rule out a player.</p><ul class="wr-list">'+(plan.concerning.length?plan.concerning.map(function(c){return '<li>'+esc(c.text.replace(/ · SMALL SAMPLE( · Lost once)?$/,""))+' <strong class="ns-sample">'+esc((c.g===1?"Lost once · ":"")+plural(c.g,"meeting")+(c.g<3?" · small sample":""))+'</strong></li>';}).join(""):'<li class="muted">No concerning direct records among remaining pairings.</li>')+'</ul></div>'
      +'<div><h3>Open risks</h3><p class="muted">Unplayed opponents with no favorable direct option left among our remaining players.</p>'+wrList(plan.risks,"None — every unplayed opponent still has a favorable direct option.")+'</div></div>';
    // Matrix
    var pair=WR_STATE.pair,pairHtml="";
    // Captain Matrix (first increment): at-a-glance flexibility. Scanning rows and columns by
    // eye to count colored cells does not scale past a few players -- this is the same category
    // rule every cell already uses, just counted, so it answers "which of my remaining players
    // has the most favorable options left?" and "which opponent is collectively hardest for my
    // remaining roster?" without opening Dangerous opponents or Best sends separately. Counts
    // only, same as every other number on this matrix -- not odds, not a ranking of players.
    var colGreen=w.theirs.map(function(o,j){
      return w.matrix.reduce(function(n,row){return n+(plan.rem[String(row.member.id)]&&row.cells[j].category==="G"?1:0);},0);
    });
    var head='<tr><th class="corner">Our player ↓ / opponent →</th>'+w.theirs.map(function(o,j){
      return '<th class="'+(plan.unplayed[j]?'':'out')+'"><a href="#rank-block-'+j+'">'+esc(playerRef(o))+'</a>'+wrNoteFlagSlot(o.id,"icon")+(plan.unplayed[j]?'':'<span class="id-line matrix-status">Played</span>')+'<span class="id-line">SL '+esc(slText(o))+'</span>'
        +'<span class="green-count" title="Favorable direct options among our remaining players">🟢×'+colGreen[j]+'</span></th>';
    }).join("")+'</tr>';
    var body=w.matrix.map(function(row,i){
      var m=row.member,out=!plan.rem[String(m.id)],status=[];
      if(wrAvail(plan.ck,m.id)==="Unavailable") status.push("Unavailable");
      if(wrLineup(plan.ck,m.id)==="Played") status.push("Played");
      var rowGreen=row.cells.filter(function(c,j){return plan.unplayed[j]&&c.category==="G";}).length;
      return '<tr class="'+(out?'out':'')+'"><th>'+esc(playerRef(m))+(status.length?'<span class="id-line matrix-status">'+esc(status.join(" · "))+'</span>':'')+'<span class="id-line">SL '+esc(slText(m))+'</span>'
        +'<span class="green-count" title="Favorable direct options among unplayed opponents">🟢×'+rowGreen+'</span></th>'
        +row.cells.map(function(c,j){
          var on=pair&&pair.our===String(m.id)&&pair.opp===String(w.theirs[j].id);
          if(on) pairHtml=wrPairDetail(w,c,w.blocks[j],fmt);
          return '<td><button type="button" class="mcell cat-'+c.category+(on?' on':'')+(plan.unplayed[j]?'':' out')+'" data-our="'+esc(m.id)+'" data-opp="'+esc(w.theirs[j].id)+'" title="'+esc(WR_CAT_LABELS[c.category]+" — "+c.explanation)+'">'+esc(WR_VIEW==="captain"?c.captain:c.cell)+'</button></td>';
        }).join("")+'</tr>';
    }).join("");
    document.getElementById("wr-matrix").innerHTML='<div class="card-head"><h2>Matchup matrix</h2><div class="mv-toggle" role="group" aria-label="Matrix view">'
      +[["captain","Captain view"],["evidence","Evidence view"]].map(function(v){return '<button type="button" class="mv'+(WR_VIEW===v[0]?' on':'')+'" data-view="'+v[0]+'" aria-pressed="'+(WR_VIEW===v[0])+'">'+v[1]+'</button>';}).join("")+'</div></div>'
      +(WR_VIEW==="captain"?'<p class="legend">🟢 Favorable direct record · 🟡 Even direct, or shared-opponent evidence only (≈) · ⚪ No verified evidence — unknown, not weak · 🔴 More direct losses than wins. Numbers are our direct record. Not odds. Tap a cell for the evidence, or switch to Evidence view for sample sizes.</p>':'')
      +'<p class="legend'+(WR_VIEW==="captain"?' print-only':'')+'"><span class="cat-dot cat-G"></span>Green = more direct wins than losses <span class="cat-dot cat-R"></span>Red = more direct losses than wins <span class="cat-dot cat-E"></span>Yellow = even direct record, or shared-opponent evidence only (≈ ours vs theirs) <span class="cat-dot cat-X"></span>Gray = no verified evidence in this snapshot. Numbers in () are meetings. Colors describe recorded results only — not odds or predictions. Where identities are unresolved or excluded a pairing’s history can be incomplete, and the missing results can move a category either way — favorable can prove concerning. Tap a cell for the evidence behind it.</p>'
      // GPT audit (issue #84, MATRIX-01): a hover title explains nothing on a phone, which has
      // no hover. 🟢×N needs a visible explanation, worded so a 0 is never read as "hardest" or
      // "safe" -- it can just as easily mean even, shared-only or no verified evidence at all.
      +'<p class="legend matrix-status-legend">Faded rows or columns are unavailable or already played. Their records and counts remain visible for reference.</p>'
      +'<p class="legend matrix-count-legend">🟢×N next to a player = favorable direct options left among unplayed opponents. 🟢×N next to an opponent = how many of your remaining players have a favorable direct record against them. 0 does not mean hardest or safe — it can mean even, shared-opponent-only or no verified evidence; check the row or column for which.</p>'
      +'<div class="table-wrap"><table class="matrix"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>'
      +'<div id="wr-pair" tabindex="-1">'+pairHtml+'</div>';
    // Lineup Lab
    var ourRows=w.ours.map(function(m){
      var a=wrAvail(plan.ck,m.id),l=wrLineup(plan.ck,m.id),pid=esc(m.id);
      return '<tr class="'+(plan.rem[String(m.id)]?'':'out')+'"><td>'+esc(playerRef(m))+'</td><td>'+esc(slText(m))+'</td>'
        +'<td><select class="plan" data-plan="avail" data-pid="'+pid+'" aria-label="Availability for '+esc(playerRef(m))+'">'+["Unknown","Available","Unavailable"].map(function(v){return '<option'+(v===a?' selected':'')+'>'+v+'</option>';}).join("")+'</select><span class="print-only">'+esc(a)+'</span></td>'
        +'<td><select class="plan" data-plan="lineup" data-pid="'+pid+'" aria-label="Lineup for '+esc(playerRef(m))+'">'+[["","—"],["Planned","Planned"],["Played","Played"]].map(function(v){return '<option value="'+v[0]+'"'+(v[0]===l?' selected':'')+'>'+v[1]+'</option>';}).join("")+'</select><span class="print-only">'+esc(l||"—")+'</span></td></tr>';
    }).join("");
    var oppRows=w.theirs.map(function(o,j){
      return '<tr class="'+(plan.unplayed[j]?'':'out')+'"><td>'+esc(playerRef(o))+'</td><td>'+esc(slText(o))+'</td><td><label class="inline"><input type="checkbox" class="plan" data-plan="played" data-pid="'+esc(o.id)+'"'+(plan.unplayed[j]?'':' checked')+'> Played</label><span class="print-only">'+(plan.unplayed[j]?'—':'Played')+'</span></td></tr>';
    }).join("");
    var cap=WR_PLAN.cap[ta.key];
    document.getElementById("lineup-lab").innerHTML='<div class="card-head"><h2>Lineup Lab</h2><button type="button" class="secondary" id="ll-clear">Clear marks for this fixture</button></div>'
      +'<p class="muted" id="ll-context">'+esc(wrCtxLabel(ta,tb))+' <span class="wr-save-scope">'+esc(wrStorageScope())+'</span> Marks change which candidates count as remaining — never the evidence. Unknown is not Unavailable. Coach notes follow the opponent player to every fixture.</p>'
      +'<div class="grid"><div><h3>Our team</h3><div class="table-wrap"><table><thead><tr><th>Player</th><th>SL</th><th>Availability</th><th>Lineup</th></tr></thead><tbody>'+ourRows+'</tbody></table></div></div>'
      +'<div><h3>Opponent</h3><div class="table-wrap"><table><thead><tr><th>Player</th><th>SL</th><th>Already played</th></tr></thead><tbody>'+oppRows+'</tbody></table></div></div></div>'
      +'<h3>Snapshot</h3><dl class="matchup-facts">'+plan.metrics.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join("")+'</dl>'
      +'<label class="cap-label">Reference skill cap (optional, user-entered)<input type="number" id="ll-cap" min="1" max="99" value="'+(cap?esc(cap):'')+'" placeholder="none — no default is assumed"></label>'
      +'<h3>Recorded options now — and why</h3><p class="muted">For each unplayed opponent: our first-listed option by recorded results, with its meeting count. Listed order is not confidence or a prediction.</p>'
      +(function(){
        var items=w.blocks.map(function(b,j){if(!plan.unplayed[j]) return null;
          var text="vs "+b.opponent_label+": "+(plan.sends[j].length?wrBestSendText(plan.sends[j]):"no evidence-backed option left among our remaining players");
          return '<li>'+esc(text)+wrNoteFlagSlot(b.opponent.id,"preview-space","your opinion, not APA facts")+'</li>';
        }).filter(Boolean);
        return '<ul class="wr-list">'+(items.length?items.join(""):'<li class="muted">'+esc("Every opponent has already played.")+'</li>')+'</ul>';
      })()
      +'<h3>Protected players — unique favorable options (consider saving)</h3><p class="muted">The only remaining favorable direct option against an unplayed opponent.</p>'+wrList(plan.unique,"None right now.");
    // Scouting cards
    document.getElementById("scouting-cards").innerHTML='<h2>Opponent scouting cards</h2><p class="muted">Full-roster history; ignores tonight’s availability marks. Use Next Send for current choices. No meetings with our roster is unknown — never a weakness. Coach observations are your notes (this browser only).</p><div class="scout-grid">'
      +w.cards.map(function(c,j){
        var pid=esc(c.opponent.id),cc=wrCoach(c.opponent.id),played=!plan.unplayed[j];
        var tagSel=function(field){return '<select class="plan" data-plan="'+field+'" data-pid="'+pid+'" aria-label="Coach tag"><option value="">—</option>'
          +WR_COACH_TAGS.map(function(t){return '<option'+(cc[field==="tag1"?"t1":"t2"]===t?' selected':'')+'>'+esc(t)+'</option>';}).join("")+'</select>';};
        var f=[["Team record",c.team_record],["League lifetime",c.lifetime],["Recorded games",c.sample],["Vs our roster",c.vs_ours],["Meetings with our players",c.met_list],["Shared-opponent evidence",c.shared_summary],["Record by opponent SL",c.by_sl],["Winning records vs",c.winning_sl],["Losing records vs",c.losing_sl],["Missing information",c.missing]];
        var hasNote=!!wrCoachSummary(c.opponent.id);
        var badges=wrQuickReadBadges(c,w.blocks[j],hasNote);
        return '<div class="scout'+(played?' out':'')+'"><div class="scout-head">'+esc(c.label)+' · SL '+esc(c.sl)+(played?' · already played':'')+'</div>'
          +'<p class="quick-read-badges">'+badges.map(function(x){return '<span>'+esc(x)+'</span>';}).join('')+'</p>'
          +'<p class="quick-read"><b>Quick read</b> '+esc(c.quick_read).replace(/\b\d+ meetings?(?:, small sample)?\b/g,function(x){return '<strong>'+x+'</strong>';})+'</p>'+wrNoteFlagSlot(c.opponent.id,"card",null,"p","ns-coach")+'<dl>'
          +f.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join("")
          +'<dt>Coach observations</dt><dd><span class="muted">Your opinion, not APA facts.</span> '+tagSel("tag1")+' '+tagSel("tag2")
          +'<textarea id="coach-note-'+pid+'" class="plan" data-plan="note" data-pid="'+pid+'" aria-label="Coach Observation for '+esc(c.label)+'" rows="2" placeholder="What you saw">'+esc(cc.n||"")+'</textarea>'
          +'<div class="coach-summary">'+esc(wrCoachSummary(c.opponent.id))+'</div>'+wrArchiveHtml(c.opponent.id)+'</dd></dl></div>';
      }).join("")+'</div>';
    // Meetings
    document.getElementById("wr-meetings").innerHTML='<h2>Direct meetings between the rosters</h2>'+(w.meetings.length
      ?'<p class="muted">Newest first · dates in '+esc(WR_TZ)+'.</p><div class="table-wrap"><table><thead><tr><th>Date</th><th>Our player</th><th>Opponent</th><th>Result (ours)</th><th>SL ours/theirs</th><th>Session</th></tr></thead><tbody>'
        +w.meetings.slice(0,60).map(function(g){return '<tr><td>'+esc(g.date)+'</td><td>'+esc(playerRef(g.our))+'</td><td>'+esc(playerRef(g.opp))+'</td><td>'+esc(g.result)+'</td><td>'+esc(wrHistoricalSLText(g.own_sl)+" / "+wrHistoricalSLText(g.opp_sl))+'</td><td>'+esc(g.session)+'</td></tr>';}).join("")+'</tbody></table></div>'
        +(w.meetings.length>60?'<p class="muted">Showing the newest 60 of '+w.meetings.length+'; Player vs Player lists every meeting.</p>':'')
      :'<p class="muted">No recorded direct meetings between these rosters in '+esc(fmtLabel(fmt))+'.</p>');
    wrPatchStorageStatus();
  }
  function wrCtxLabel(ta,tb){
    var c=MATCHUP_CONTEXT;
    if(c&&c.ourKey===ta.key&&c.oppKey===tb.key&&c.fixture) return "Marks for this fixture only ("+(c.fixture.local_display||"undated fixture")+").";
    return "Teams picked by hand — not a Match Day fixture. Marks here are kept apart from every fixture's marks.";
  }
  function wrPairDetail(w,row,block,fmt){
    var m=row.member,o=block.opponent,mm=oppMap(m.id,fmt),om=oppMap(o.id,fmt);
    var shared=Object.keys(mm).filter(function(k){return !!om[k];}).sort(function(a,b){var d=(mm[b].g+om[b].g)-(mm[a].g+om[a].g);if(d) return d;var na=PLAYERS[a]?PLAYERS[a].name:a,nb=PLAYERS[b]?PLAYERS[b].name:b;return na<nb?-1:(na>nb?1:0);});
    var games=w.meetings.filter(function(g){return String(g.our.id)===String(m.id)&&String(g.opp.id)===String(o.id);});
    return '<div class="pair cat-border-'+row.category+'"><a class="pair-return" href="#next-send">Back to Next Send</a><h3>'+esc(playerRef(m))+' vs '+esc(playerRef(o))+'</h3>'
      +'<p>'+wrChip(row.category)+' <b>'+esc(WR_CAT_LABELS[row.category])+'</b> · rank '+esc(row.rank)+' of '+block.rows.length+' vs this opponent · '+esc(row.explanation)+'</p>'
      +(games.length?'<h4>Direct meetings</h4><div class="table-wrap"><table><thead><tr><th>Date</th><th>Result (ours)</th><th>SL ours/theirs</th><th>Session</th></tr></thead><tbody>'+games.map(function(g){return '<tr><td>'+esc(g.date)+'</td><td>'+esc(g.result)+'</td><td>'+esc(wrHistoricalSLText(g.own_sl)+" / "+wrHistoricalSLText(g.opp_sl))+'</td><td>'+esc(g.session)+'</td></tr>';}).join("")+'</tbody></table></div>':'<p class="muted">No verified direct meetings in this snapshot.</p>')
      +(shared.length?'<h4>Shared opponents ('+shared.length+')</h4><div class="table-wrap"><table><thead><tr><th>Shared opponent</th><th>'+esc(playerRef(m))+' vs them</th><th>'+esc(playerRef(o))+' vs them</th></tr></thead><tbody>'
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
      if((k==="tag1"||k==="tag2")&&t.getAttribute("data-pid")){
        wrSetCoach(t.getAttribute("data-pid"),k==="tag1"?"t1":"t2",t.value);
        wrPatchCoachObservation(t.getAttribute("data-pid"));
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
      if(t&&t.id==="ll-cap"&&cur.ta){
        var v=parseFloat(t.value);
        if(isFinite(v)&&v>0) WR_PLAN.cap[cur.ta.key]=v; else delete WR_PLAN.cap[cur.ta.key];
        wrSave();
        if(cur.tb&&cur.ta.players.length&&cur.tb.players.length){
          var w=warRoomPair(cur.ta,cur.tb,TF.value);
          wrPatchBudget(w,wrPlan(w,cur.ta,cur.tb),cur.ta);
        }
        return;
      }
      if(!t||!t.getAttribute||t.getAttribute("data-plan")!=="note"||!cur.tb) return;
      var npid=t.getAttribute("data-pid");
      wrSetCoach(npid,"n",t.value);
      // The exact no-observation sentinel and note slots are opinion metadata only.
      wrPatchCoachObservation(npid);
    });
    root.addEventListener("click",function(ev){
      var t=ev.target&&ev.target.closest?ev.target.closest("button"):null;
      if(!t) return;
      var cur=current();
      if(t.id==="ll-clear"&&cur.ta&&cur.tb){var ck=wrCtx(cur.ta,cur.tb);delete WR_PLAN.our[ck];delete WR_PLAN.opp[ck];wrSave();renderTeamMatchups();return;}
      if(t.hasAttribute("data-view")){WR_VIEW=t.getAttribute("data-view")==="captain"?"captain":"evidence";
        try{window.localStorage.setItem("ultimate-coach:matrix-view",WR_VIEW);}catch(e){}
        renderTeamMatchups();var b=root.querySelector('.mv[data-view="'+WR_VIEW+'"]');if(b) b.focus();return;}
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
      if(t.hasAttribute("data-inspect-our")){
        // Inspect the existing evidence without selecting a future opponent as the actual put-up.
        WR_STATE.pair={our:t.getAttribute("data-inspect-our"),opp:t.getAttribute("data-inspect-opp")};
        renderTeamMatchups();
        var detail=document.getElementById("wr-pair");if(detail){detail.focus({preventScroll:true});detail.scrollIntoView({block:"start"});}
        return;
      }
      if(t.hasAttribute("data-next")){WR_STATE.next=t.getAttribute("data-next");renderTeamMatchups();
        var again=el.querySelector('.ns-chip.on');if(again) again.focus();return;}
      if(t.hasAttribute("data-send-our")&&ta&&tb){var ck=wrCtx(ta,tb);
        // One Sent action saves both marks together; a rejected write must not leave half a pairing.
        wrSetMark("our",ck,t.getAttribute("data-send-our"),"l","Played",true);wrSetMark("opp",ck,t.getAttribute("data-send-opp"),"p",true);
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
