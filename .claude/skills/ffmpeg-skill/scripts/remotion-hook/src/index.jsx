import React from 'react';
import {registerRoot,Composition,AbsoluteFill,useCurrentFrame,useVideoConfig,spring,interpolate,staticFile} from 'remotion';
const Hook=({title,emphasis,brand,episode,color})=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig();
 const a=spring({frame:f-8,fps,config:{damping:18,stiffness:130}});
 const b=spring({frame:f-32,fps,config:{damping:13,stiffness:140}});
 const end=interpolate(f,[135,149],[1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
 return <AbsoluteFill style={{background:'radial-gradient(ellipse at 90% 30%,#514019 0%,#15191b 45%,#090b0c 100%)',color:'white',fontFamily:'BenThai',padding:90,justifyContent:'center',opacity:end}}>
 <style>{`@font-face{font-family:BenThai;src:url('${staticFile('Thai.ttf')}')}`}</style>
 <div style={{position:'absolute',top:220,left:90,color,fontSize:42,letterSpacing:3}}>{episode}</div>
 <div style={{fontSize:70,lineHeight:1.55,transform:`translateY(${(1-a)*70}px)`,opacity:Math.min(1,a)}}>{title}</div>
 <div style={{fontSize:156,lineHeight:1.5,color,transform:`scale(${0.82+b*0.18})`,transformOrigin:'left center',opacity:Math.min(1,b)}}>{emphasis}</div>
 <div style={{height:12,width:interpolate(f,[30,65],[0,760],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}),background:color,borderRadius:9}}/>
 <div style={{position:'absolute',bottom:300,left:90,fontSize:42,color:'#d4d4d4'}}>{brand}</div>
 </AbsoluteFill>;
};
const Root=()=> <Composition id="BenHook" component={Hook} width={1080} height={1920} fps={30} durationInFrames={150} defaultProps={{title:'',emphasis:'',brand:'',episode:'',color:'#ffe457'}}/>;
registerRoot(Root);
