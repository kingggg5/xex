/** Cosmetic timing inside the remaining authoritative state window.
 * Reserve one server tick for impact; short active states show impact now.
 * Repeated active snapshots retain the current pose instead of resetting idle.
 */
export function monsterActiveMotion(previousState,remainingStateTicks) {
	if(!Number.isInteger(remainingStateTicks)||remainingStateTicks<0||remainingStateTicks>65535)throw new RangeError('Invalid monster state tick count');
	if(previousState===3)return {phase:null,impactDelayMs:0};
	const impactDelayMs=Math.min(110,Math.max(0,remainingStateTicks-1)*50);
	return {phase:impactDelayMs>0?'leap':'impact',impactDelayMs};
}
