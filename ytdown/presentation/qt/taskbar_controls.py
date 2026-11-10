"""Liga os controles externos ao estado confirmado pelo player."""

from ytdown.application.ports import PlayerState, ThumbnailControls


class TaskbarPlayback:
    def __init__(self, playback, controls: ThumbnailControls):
        self.playback = playback
        self.controls = controls
        playback.add_listener(self)
        controls.set_playing(playback.state is PlayerState.PLAYING)

    def on_state_changed(self, state):
        self.controls.set_playing(state is PlayerState.PLAYING)

    def on_track_changed(self, track): pass
    def on_position_changed(self, position, duration): pass
    def on_queue_changed(self): pass
    def on_track_unavailable(self, track, message): pass
    def on_settings_changed(self): pass

    def shutdown(self):
        if self.playback is not None:
            self.playback.remove_listener(self)
            self.playback = None
            self.controls.shutdown()
