export interface ProgressionState {characterId:string;revision:number;level:number;jobLevel:number;statPoints:number}
export interface ProgressionCue {level:number;jobLevel:number;baseLevelsGained:number;jobLevelsGained:number;pointsAvailable:number}
export class ProgressionFeedback {reset():void;accept(value:ProgressionState):Readonly<ProgressionCue>|null}
