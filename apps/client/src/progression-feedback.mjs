/** Presentation from confirmed character state; never calculates or awards EXP/points. */
export class ProgressionFeedback {
 #previous=null;
 reset(){this.#previous=null;}
 accept(value){
  if(!value||typeof value.characterId!=='string'||!value.characterId||value.characterId.length>120||!['revision','level','jobLevel','statPoints'].every(k=>Number.isSafeInteger(value[k])&&value[k]>=0)||value.level<1||value.jobLevel<1)return null;
  const next={...value},previous=this.#previous;
  if(!previous||previous.characterId!==next.characterId){this.#previous=next;return null;}
  if(next.revision<=previous.revision)return null;
  this.#previous=next;
  const baseLevelsGained=Math.max(0,next.level-previous.level),jobLevelsGained=Math.max(0,next.jobLevel-previous.jobLevel);
  if(!baseLevelsGained&&!jobLevelsGained)return null;
  return Object.freeze({level:next.level,jobLevel:next.jobLevel,baseLevelsGained,jobLevelsGained,pointsAvailable:next.statPoints});
 }
}
