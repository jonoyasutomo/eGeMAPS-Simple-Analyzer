# Speech Feature Analyzer for eGeMAPSv02 v1.1.0

Formerly released as **eGeMAPS Simple Analyzer** in the v1.0.x series.

Speech Feature Analyzer for eGeMAPSv02 is a Windows research-support GUI application that externally runs an official copy of openSMILE obtained separately by the user. It supports semi-automatic speech interval estimation, extraction of openSMILE/eGeMAPSv02 acoustic features, and calculation of speech behavior measures.

## Main features

- Import of WAV, M4A, MP3, MP4, AAC, and FLAC files
- Automatic conversion to an analysis-ready mono 16-bit PCM WAV file
- Waveform display
- Semi-automatic speech interval estimation based on eGeMAPSv02 LLD loudness
- Extraction of eGeMAPSv02 Functionals
- Calculation of:
  - speech onset latency
  - total speaking time
  - speech ratio
  - pause count
  - mean pause duration
- CSV export of acoustic features, speech behavior measures, and analysis settings

## Required openSMILE installation

**openSMILE is not included with this software.**

Users must download the official 64-bit Windows release of openSMILE from:

https://github.com/audeering/opensmile/releases

Extract the downloaded archive and place the extracted openSMILE folder in the same directory as the executable.

Recommended arrangement:

```text
Speech_Feature_Analyzer_for_eGeMAPSv02/
├─ Speech_Feature_Analyzer_for_eGeMAPSv02_v1.1.0.exe
├─ README.md
├─ LICENSE.txt
└─ opensmile-3.0.2-windows-x86_64/
   ├─ bin/
   │  └─ SMILExtract.exe
   └─ config/
      └─ egemaps/
         └─ v02/
            └─ eGeMAPSv02.conf
```

A differently named openSMILE folder can also be used. If automatic detection fails, click **Select official openSMILE folder** in the application and select the top-level folder of the extracted openSMILE package.

## How to use

1. Download and extract the official Windows version of openSMILE.
2. Place the extracted openSMILE folder in the same directory as the executable.
3. Double-click `Speech_Feature_Analyzer_for_eGeMAPSv02_v1.1.0.exe`.
4. Confirm that the application reports that official openSMILE is configured.
5. Enter a Participant ID.
6. Select an audio file.
7. Review the waveform, reference silence intervals, loudness curve, and estimated analysis interval.
8. Modify the reference silence intervals only when the estimate is clearly incorrect.
9. Click **Start analysis**.
10. Save the results as CSV.

## Recommended recording procedure

- Leave approximately 5 seconds of silence after recording starts and before speech begins.
- Leave approximately 5 seconds of silence after speech ends and before recording stops.
- Avoid the examiner's voice, coughing, desk contact noise, clothing noise, and recording-operation noise in the reference silence intervals.

Default reference silence intervals:

- Pre-speech: 1.0–4.0 seconds after recording starts
- Post-speech: from 4.0 seconds before the end of the recording to 1.0 second before the end

A warning is displayed if either reference silence interval is shorter than 1 second. Whenever possible, use approximately 3 seconds of quiet reference silence.

## Speech interval estimation

The application calculates a speech-detection threshold using the 95th percentile of eGeMAPSv02 LLD loudness values in the pre-speech and post-speech reference silence intervals.

Processing rules:

- Loudness smoothing: 100 ms moving average
- Speech detection: loudness remains above the threshold for at least 200 ms
- Analysis start: 50 ms before the estimated speech onset candidate
- Analysis end: 100 ms after the estimated speech offset candidate
- Pause definition: loudness remains at or below the threshold for at least 200 ms

These are processing rules adopted by this application. They are not official silence-detection criteria defined by openSMILE or eGeMAPSv02.

## Speech behavior measures

The following measures are calculated by the application:

- `onset_latency_sec`: time from recording start to the estimated speech onset candidate
- `total_speaking_sec`: total time above the threshold within the speech candidate interval
- `speech_ratio`: estimated speaking time divided by the analysis interval duration
- `pause_count`: number of pauses lasting at least 200 ms
- `mean_pause_duration_sec`: mean duration of pauses lasting at least 200 ms

These measures are not eGeMAPSv02 Functionals. They are derived by this application using eGeMAPSv02 LLD loudness.

## Important notes

- The results are research-support measures and are not intended for diagnosis or individual clinical judgment.
- Results may vary with audio quality, environmental noise, microphone position, speech task, and recording format.
- Recording conditions and procedures should be standardized when comparing participants or conditions.
- This software does not modify openSMILE itself or the feature definitions of eGeMAPSv02.
- This software externally runs openSMILE obtained separately by the user.

## License and third-party software

This software is released under the MIT License. See `LICENSE.txt`.

openSMILE is separate third-party software and is not included. Users must review and comply with the official openSMILE license terms:

https://audeering.github.io/opensmile/about.html

FFmpeg and imageio-ffmpeg components used for audio conversion remain subject to their respective licenses.

## Version

**Speech Feature Analyzer for eGeMAPSv02 v1.1.0**

## Disclaimer

This software is provided “as is,” without warranty of any kind. The copyright holder and developers are not liable for direct or indirect damages arising from its use.
