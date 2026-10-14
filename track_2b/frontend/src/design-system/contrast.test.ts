import { expect, it } from 'vitest';
function luminance(hex:string){const rgb=hex.replace('#','').match(/../g)!.map(value=>parseInt(value,16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;}
function contrast(a:string,b:string){const values=[luminance(a),luminance(b)].sort((a,b)=>b-a);return (values[0]+.05)/(values[1]+.05);}
it('keeps the specified text, status and control states above contrast thresholds',()=>{
  for(const [text,background] of [['#182F32','#F7F8F4'],['#4F6768','#FFFFFF'],['#125B55','#FFFFFF'],['#FFFFFF','#125B55'],['#8A2632','#FCEFF0'],['#705016','#FCF3DA'],['#55615A','#E6EAE6']])expect(contrast(text,background)).toBeGreaterThanOrEqual(4.5);
  expect(contrast('#996500','#FFFFFF')).toBeGreaterThanOrEqual(3);
  expect(contrast('#718781','#FFFFFF')).toBeGreaterThanOrEqual(3);
});
