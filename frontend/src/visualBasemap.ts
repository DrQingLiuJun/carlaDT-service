// Visual tracing registered to the long straight CARLA lane centres.
// Pixel coordinates refer to the 2048×719 source view. +X right, +Y down.
export const hautBasemap={url:'/maps/haut-visual.svg?v=4',scale:14.8,originX:1027,originY:366.8,width:2048,height:719};
export function visualBounds(name:string):number[]|null{
 if(name!=='HAUT_Map')return null;
 const b=hautBasemap;
 return [-b.originX/b.scale,-b.originY/b.scale,(b.width-b.originX)/b.scale,(b.height-b.originY)/b.scale];
}
