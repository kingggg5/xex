/** Six frozen main-map framing contracts; actor witnesses remain on the existing Y0 routes. */
const VIEWS=Object.freeze({
 spawn:{target:{x:0,y:1.2,z:-4},player:{x:0,z:-11},radius:null},
 elevated:{target:{x:0,y:1,z:-51},player:{x:0,z:-11},radius:120},
 arena:{target:{x:0,y:1.2,z:-68},player:{x:0,z:-84},radius:null},
 cove:{target:{x:-45,y:1,z:-78},player:{x:-42,z:-84},radius:null},
 croft:{target:{x:38.6,y:1.2,z:-19},player:{x:31,z:-20},radius:null},
 knoll:{target:{x:31,y:4,z:-95},player:{x:7,z:-97},radius:null},
});
export function blueprintReviewView(key='spawn'){
 const view=VIEWS[key];if(!view)throw new RangeError(`Unknown blueprint view ${key}`);
 return {key,target:{...view.target},player:{...view.player},radius:view.radius};
}
