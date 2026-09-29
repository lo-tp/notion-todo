import React from "react";
import {Composition} from "remotion";
import {DemoVideo, TOTAL_DURATION} from "./DemoVideo";

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="DemoVideo"
      component={DemoVideo}
      width={WIDTH}
      height={HEIGHT}
      fps={FPS}
      durationInFrames={TOTAL_DURATION}
    />
  );
};
