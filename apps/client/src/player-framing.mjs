/** Player presentation, independent of server movement/radius and asset topology. */
export function playerFraming(search='',portrait=false,dev=false){
 const legacy=dev&&new URLSearchParams(search).get('heroFraming')==='legacy';
 return Object.freeze(legacy
  ?{radius:13,beta:1.18,fov:portrait?.98:1.02,avatarScale:1,targetHeight:1.65,lookAhead:2,upperBeta:1.25}
  :{radius:11.2,beta:1.26,fov:portrait?.90:.78,avatarScale:1.10,targetHeight:1.45,lookAhead:2,upperBeta:1.35});
}
