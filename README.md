Queue Processor
===============

Purpose
-------
This project began as a way to queue up files for [HandBrakeCLI](https://trac.handbrake.fr/wiki/CLIGuide), and that is how I use it today. The script picks one file from the input directory(-ies), runs a command on it to produce an output file, moves that output file to a destination, then deletes the input file. It only processes a single file; it's intended to be run frequently by a scheduler.

As I wrote more and more code I realized that it didn't need to be HandBrakeCLI- or encoding-specific at all. If you're using this to do something other than manage a HandBrakeCLI queue, I'd love to hear about it.

Basic Usage
-----------
I run this script in a cron job, like so:

	*/5 * * * * CMD="/Volumes/Drobo/Code/queue/queue.py"; test -x "$CMD" && "$CMD"

The script contains a locking mechanism that should ensure only one copy can run at a time; if it's already running, it will quietly exit with no output. Testing for the existence of the script before running it also allows me to disconnect the external drive it lives on without getting cron errors.

The script will create a subdirectory under the script's location with the same name as the machine running the script. Into that subdirectory it will write its log files and also store the stdout and stderr of the processes it runs.

There are two command-line flags and one command-line arguement, all optional:

* `--verbose` - Causes the script to output a lot of information to the log about what it's doing and how it was configured.
* `--debug` - Causes the script to output its logs to the screen instead of a file, and also causes the script to not actually do anything. It won't run any processes or create or remove any files.
* config file - If you put a filename on the command-line, that file will be used as the config file, explained below.

`--debug` implies `--verbose`, so you don't need to use both.

Config File
-----------
The actions of the script are configured by entries in a [JSON](http://www.w3schools.com/json/json_syntax.asp) file called `queue.json`. You can have a `queue.json` file in the machine-specific subdirectory, but if one is not found there it will default to the one in the same directory as the script.

### Minimal `queue.json` Example

	{
	    "incoming_paths": "/path/to/input/files",
	    "file_filters": "*",
	    "call": [
	        "/path/to/executable",
	        "%(input_file)s",
	        "%(output_file)s"
	    ],
	    "failed_path": "/path/to/failed/files",
	    "destination_base": "/path/to/output/files"
	}

This config includes all the mandatory sections.

* `incoming_paths` - This is where the script will find input files. It can be a single directory or a list of them. If a list, the script will examine each one in turn until it finds a file to process.
* `file_filters` - This is wildcard/glob that will be used to create a list of files in the input directories. It can be a single pattern or a list of them. If a list, the script will apply all of them at once to come up with a single list of files to choose from.
* `call` - This is the program and arguements the script will call for the input file it chooses. It supports variable substitution; more detail on that below, but the variables `%(input_file)s` and `%(output_file)s` will be provided by the script and should be used by the program.
* `failed_path` - This is where the input file will be moved if the program lauched by the script fails, in order to remove it from being reprocessed again and again.
* `destination_base` - This is where the output file will be moved when the program lauched by the script completes.

### Full `queue.json` Example

	{
	    "incoming_paths": [
	        "/Volumes/Drobo/Incoming/Priority",
	        "/Volumes/Drobo/Incoming/TiVo",
	        "/Volumes/Drobo/Incoming/TV",
	        "/Volumes/Drobo/Incoming/Film",
	        "/Volumes/Drobo/Incoming/Animation",
	        "/Volumes/Drobo/Incoming/Watched"
	    ],
	    "in_order": [
	        "/Volumes/Drobo/Incoming/TiVo",
	        "/Volumes/Drobo/Incoming/TV"
	    ],
	    "file_filters": [
	        "*.mkv",
	        "*.mp4",
	        "*.m4v",
	        "*.mpg",
	        "*.mpeg",
	        "*.mov",
	        "*.avi"
	    ],
	    "call": [
	        "%(handbrake)s",
	        "--verbose",
	        "--input", "%(input_file)s",
	        "--main-feature",
	        "--previews", "50",
	        "--output", "%(output_file)s",
	        "--markers",
	        "--large-file",
	        "--optimize",
	        "--encoder", "x264",
	        "--x264-preset", "%(h264-preset)s",
	        "--x264-tune", "%(h264-tuning)s",
	        "--h264-profile", "%(h264-profile)s",
	        "--h264-level", "%(h264-level)s",
	        "--vb", "%(video-bitrate)s",
	        "--two-pass",
	        "--turbo",
	        "--pfr",
	        "--rate", "30",
	        "--audio", "1",
	        "--aencoder", "faac",
	        "--ab", "%(audio-bitrate)s",
	        "--mixdown", "dpl2",
	        "--arate", "auto",
	        "--audio-copy-mask", "aac,ac3,dtshd,dts,mp3",
	        "--audio-fallback", "ffac3",
	        "--maxWidth", "%(maxWidth)s",
	        "--maxHeight", "%(maxHeight)s",
	        "--loose-anamorphic",
	        "--modulus", "2",
	        "--subtitle", "scan",
	        "--subtitle-forced",
	        "--subtitle-burned"
	    ],
	    "call_vars": {
	        "audio-bitrate": "160",
	        "h264-level": "4.0",
	        "h264-preset": "slower",
	        "h264-profile": "main",
	        "h264-tuning": "film",
	        "handbrake": "/Applications/kmttg/handbrake/HandBrakeCLI",
	        "maxHeight": "720",
	        "maxWidth": "1280",
	        "video-bitrate": "3995"
	    },
	    "conditional_vars": {
	        ".mkv": {
	            "h264-preset": "veryslow"
	        },
	        "/Animation/": {
	            "h264-tuning": "animation"
	        },
	        "/TiVo/": {
	            "h264-preset": "medium",
	            "video-bitrate": "2995"
	        },
	        "/TV/": {
	            "h264-preset": "slow",
	            "video-bitrate": "2995"
	        }
	    },
	    "output_ext": "mp4",
	    "timeout": 18,
	    "failed_path": "/Volumes/Drobo/Incoming/Failed",
	    "destination_base": "/Volumes/Drobo/Plex",
	    "default_subdir": "Movies",
	    "conditional_subdir": {
	        "/TiVo/": "TiVo",
	        "/TV/": "TV Shows"
	    }
	}

In addition to the mandatory config sections above, this example shows some new, optional ones.

* `in_order` - The default bahavior when the script finds more than one file is to pick one randomly. For the directories in this list, the file chosen will be the first one alphabetically. This is meant for TV shows, where you'd want to process the seasons and episodes in order.
* `call_vars` - In addition to the script-generated `%(input_file)s` and `%(output_file)s`, the `call` arguements can include your own variables. `call_vars` is where you put the default values for those custom variables.
* `conditional_vars` - This section lets you modify your custom variables based on the full path of the input file. This section is a dict of dicts. Each key in this section is compared to the full path of the input file, including the filename. If there's a match, then the values under that key are used instead of the values from the `call_vars` section. **Note:** If more than one key matches the input path, they will *all* be applied, but in no particular/deterministic order. You may get unexpected behavior if you set the same variable more than once.
* `output_ext` - The output file will be forced to have this file extension. The default behavior is for the output file to have the same extension as the input file.
* `timeout` - If this section is present and the `subprocess32` module is available, the subprocess launched will only be allowed to run for this many hours before being killed and marked as failed. **Note:** This number is in **hours**, not seconds.
* `default_subdir` - If this section is present, then the output file will be moved into this subdirectory of the path specified in `destination_base`.
* `conditional_subdir` - This section behaves similarly to the `conditional_vars` section. Each key will be tested against the full input file path; if there's a match, its value will be used as the subdirectory under `destination_base`.

Multiple Machines
-----------------
This script is designed to allow multiple machines to work on different files from the same queue. The different running scripts don't communicate directly with each other, but use files written to the machine subdirectories to indicate which file is being processed and avoid processing the same file in parallel. I believe the implimentation is rubust, but it's probably not foolproof. Comments are welcomed.

All the machines that are sharing the same input directories should share the same script directory to ensure they're all able to find each other's "marker" files. I export and mount the whole volume that contains input, output, and script diretories, but I'm sure more complicated and specific setups would also work. Machine-specific configuration files allow different machines to share many aspects while also including needed differences, such as the path to the executable in the `call` section.

Cross-Platform Testing
----------------------
This script was written on and runs on a Mac. I've tried to use only cross-platform Python functions for all operations... with the exception of file locking. There is no built-in cross-platform file locking support in Python, so I'm using the small [portalocker](http://code.activestate.com/recipes/65203/) module that I discovered while looking into this problem.

I've been blessed and haven't been forced to use a Windows machine for years, so I don't have one available to test this script or its locking behavior. If you run this script on Windows and find that it works (or doesn't), I'd love to hear about your experience.

Basic testing has been done on a Linux machine, as well. The locking mechanism works, and the config file parses and debug output looks normal. I have no reason to believe that it won't be fully functional on Linux or other POSIX Unix machines.

`manage_logs.sh`
----------------
Because this script creates individual log files every time it is run, and the stdout and/or stderr files can sometimes be quite large, I've included a small script called `manage_logs.sh` to help keep them organized. I run it from cron hourly, and it performs these actions:

1. Collect all logs entries and put them into a single log file called `combined.log`. This uses `sort -u` so each entry will only appear once and in order.
1. Remove all log files more than 36 hours old.
1. Remove all empty stdout and stderr files more than 36 hours old.
1. Compress all stdout and stderr files more than 36 hours old.
1. Remove all compressed files more than 7 days old.

Both the 36 hour and 7 day times can be passed in on the command-line if you'd like to use different timeframes.

Sample Debug Output
-------------------
This is an example of script debug output using the full config, above.

	[04/01/16 19:57:12] Search paths: /Volumes/Drobo/Incoming/Priority /Volumes/Drobo/Incoming/TiVo /Volumes/Drobo/Incoming/TV /Volumes/Drobo/Incoming/Film /Volumes/Drobo/Incoming/Animation /Volumes/Drobo/Incoming/Watched
	[04/01/16 19:57:12] File filters: *.mkv *.mp4 *.m4v *.mpg *.mpeg *.mov *.avi
	[04/01/16 19:57:12] Destination base: /Volumes/Drobo/Plex
	[04/01/16 19:57:12] Output extension: mp4
	[04/01/16 19:57:12] Default call: /Applications/kmttg/handbrake/HandBrakeCLI --verbose --input fake input --main-feature --previews 50 --output fake output --markers --large-file --optimize --encoder x264 --x264-preset slower --x264-tune film --h264-profile main --h264-level 4.0 --vb 3995 --two-pass --turbo --pfr --rate 30 --audio 1 --aencoder faac --ab 160 --mixdown dpl2 --arate auto --audio-copy-mask aac,ac3,dtshd,dts,mp3 --audio-fallback ffac3 --maxWidth 1280 --maxHeight 720 --loose-anamorphic --modulus 2 --subtitle scan --subtitle-forced --subtitle-burned
	[04/01/16 19:57:12] Base: /Volumes/Drobo/Incoming/Film
	[04/01/16 19:57:12] All files: /Volumes/Drobo/Incoming/Film/video1.mkv /Volumes/Drobo/Incoming/Film/video2.mkv
	[04/01/16 19:57:12] Currently processing:
	[04/01/16 19:57:12] Available files: /Volumes/Drobo/Incoming/Film/video1.mkv /Volumes/Drobo/Incoming/Film/video2.mkv
	[04/01/16 19:57:12] Picked (randomly): /Volumes/Drobo/Incoming/Film/video2.mkv
	[04/01/16 19:57:22] Conditional '.mkv': h264-preset = veryslow
	[04/01/16 19:57:22] Starting processing: video2.mkv
	[04/01/16 19:57:22] Calling: /Applications/kmttg/handbrake/HandBrakeCLI --verbose --input /Volumes/Drobo/Incoming/Film/video2.mkv --main-feature --previews 50 --output /var/folders/9d/17z33pg970505lb23rh3m68s5m4zwc/T/video2.mp4 --markers --large-file --optimize --encoder x264 --x264-preset veryslow --x264-tune film --h264-profile main --h264-level 4.0 --vb 3995 --two-pass --turbo --pfr --rate 30 --audio 1 --aencoder faac --ab 160 --mixdown dpl2 --arate auto --audio-copy-mask aac,ac3,dtshd,dts,mp3 --audio-fallback ffac3 --maxWidth 1280 --maxHeight 720 --loose-anamorphic --modulus 2 --subtitle scan --subtitle-forced --subtitle-burned
	[04/01/16 19:57:22] Default subdir: Movies
	[04/01/16 19:57:22] Filing into 'Movies': video2
	[04/01/16 19:57:22] Moving /var/folders/9d/17z33pg970505lb23rh3m68s5m4zwc/T/video2.mp4
	[04/01/16 19:57:22]  ..to /Volumes/Drobo/Plex/Movies
	[04/01/16 19:57:22]  ..through /Volumes/Drobo
	[04/01/16 19:57:22] Removing: /Volumes/Drobo/Incoming/Film/video2.mkv

