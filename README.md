eGeMAPS Simple Analyzer v1.0.0
README (Windows)

1. About This Software
eGeMAPS Simple Analyzer is a research-support GUI application that externally runs an official copy of openSMILE obtained separately by the user. It supports acoustic feature extraction with eGeMAPSv02 and semi-automatic estimation of speech analysis intervals.

Main features
- Import of wav / m4a / mp3 / mp4 / aac / flac files
- Automatic conversion to an analysis-ready WAV file
- Waveform display
- Semi-automatic speech interval estimation based on eGeMAPSv02 LLD loudness
- Extraction of eGeMAPSv02 Functionals
- Calculation of speech onset latency, total speaking time, speech ratio, pause count, and mean pause duration
- Export of analysis settings and results to CSV

2. Distributed Files
The following files are typically placed in the same folder:

eGeMAPS_Simple_Analyzer/
├─ eGeMAPS_Simple_Analyzer.exe
├─ README.txt
├─ LICENSE.txt
└─ opensmile-3.0.2-windows-x86_64/
   ├─ bin/
   │  └─ SMILExtract.exe
   └─ config/
      └─ egemaps/
         └─ v02/
            └─ eGeMAPSv02.conf

Important:
openSMILE itself is not included with this software.

Users must download the official 64-bit Windows version of openSMILE from the official distribution source, extract it, and place the extracted folder in the same directory as eGeMAPS_Simple_Analyzer.exe.

Official releases:
https://github.com/audeering/opensmile/releases

Recommended folder name:
opensmile-3.0.2-windows-x86_64

A different folder name can also be used, as long as it contains both SMILExtract.exe and eGeMAPSv02.conf. In that case, use the "Select official openSMILE folder" button in the application to specify the folder.

3. How to Start
1) Download the official Windows version of openSMILE and extract it.
2) Place the extracted openSMILE folder in the same folder as eGeMAPS_Simple_Analyzer.exe.
3) Double-click eGeMAPS_Simple_Analyzer.exe.
4) Confirm that the top of the window shows that official openSMILE has been configured.
5) If openSMILE is not configured, click "Select official openSMILE folder" and select the extracted openSMILE folder.
6) Enter a Participant ID and select an audio file.
7) Review the reference silence intervals, waveform, loudness curve, and estimated analysis interval.
8) Only when necessary, modify the reference silence intervals and click "Re-estimate from reference silence intervals."
9) Click "Start analysis."
10) After analysis, click "Save all analysis results as CSV."

4. Recommended Recording Procedure
- After recording starts, leave approximately 5 seconds of silence before speech begins.
- After speech ends, leave approximately 5 seconds of silence before stopping the recording.
- Avoid including the examiner's voice, coughing, desk contact noise, clothing noise, or recording operation noise in the reference silence intervals.

Default reference silence intervals
- Pre-speech interval: 1.0 to 4.0 seconds after recording starts
- Post-speech interval: from 4.0 seconds before the end of the recording to 1.0 second before the end

A warning is displayed if either reference silence interval is shorter than 1 second.
Whenever possible, use approximately 3 seconds of quiet reference silence.

5. Speech Interval Estimation
The application calculates a speech-detection threshold using the 95th percentile of eGeMAPSv02 LLD loudness values in the pre-speech and post-speech reference silence intervals.

Processing rules
- Loudness smoothing: 100 ms moving average
- Speech detection: loudness remains above the threshold for at least 200 ms
- Analysis start: 50 ms before the estimated speech onset candidate
- Analysis end: 100 ms after the estimated speech offset candidate
- Pause definition: loudness remains at or below the threshold for at least 200 ms

These are processing rules adopted by this application. They are not official silence-detection criteria defined by openSMILE or eGeMAPSv02.

6. Speech Behavior Measures
The application calculates the following speech behavior measures:

- onset_latency_sec:
  Time from recording start to the estimated speech onset candidate

- total_speaking_sec:
  Total duration during which loudness is above the threshold within the speech candidate interval

- speech_ratio:
  Proportion of estimated speaking time within the analysis interval

- pause_count:
  Number of pauses lasting at least 200 ms

- mean_pause_duration_sec:
  Mean duration of pauses lasting at least 200 ms

These measures are not eGeMAPSv02 Functionals. They are calculated by this application using eGeMAPSv02 LLD loudness.

7. Important Notes
- Results are intended as research-support measures and are not intended for diagnosis or individual clinical judgment.
- Results may be affected by audio quality, environmental noise, microphone position, speech task, and recording format.
- When comparing conditions, standardize the recording environment and procedure as much as possible.
- This software does not modify openSMILE itself or the feature definitions of eGeMAPSv02.
- This software is an independent GUI support tool that externally runs openSMILE obtained separately by the user.

8. openSMILE License
openSMILE is third-party software and is separate from eGeMAPS Simple Analyzer.

Users are responsible for reviewing and complying with the official openSMILE license terms when obtaining and using openSMILE.

Official licensing information:
https://audeering.github.io/opensmile/about.html

According to the official information, the open-source version is intended for private, research, and educational use, while commercial use is subject to restrictions. Users considering commercial use should contact the rights holder of openSMILE.

9. Positioning of This Software
eGeMAPS Simple Analyzer is a research-support GUI application built on acoustic feature extraction with openSMILE/eGeMAPSv02. It integrates speech behavior measures such as speech onset latency and pause duration and semi-automatically estimates the analysis interval.

The software is intended to reduce examiner dependence associated with manual specification of analysis intervals and to support improved reproducibility of speech analysis procedures.

10. Version
eGeMAPS Simple Analyzer v1.0.0

11. Disclaimer
This software is provided "as is."

The copyright holder and developers are not liable for any direct or indirect damages arising from the use of this software.
