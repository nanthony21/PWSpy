import copy
from abc import ABC, abstractmethod

from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.widgets import AxesWidget

from pwspy.utility.matplotlibWidgets.coreClasses import AxManager




class SelectorWidgetBase(AxesWidget, ABC):
    """Base class for other selection widgets in this file. Requires to be managed by an AxManager. Inherited classes
    can implement a number of action handlers like mouse actions and keyboard presses.
    button allows the user to specify which mouse buttons are valid to trigger an event. This can be an int or list of ints.
    state_modifier_keys should be a dict {state: keyName}, the default is {move=' ', clear='escape', square='shift', center='control'}"""
    def __init__(self, axMan: AxManager, image: AxesImage, onselect=None, button=None, state_modifier_keys=None):
        AxesWidget.__init__(self, axMan.ax)
        self.onselect = onselect
        self.visible = True
        self.axMan = axMan
        self.image = image
        self.artists = []
        self.connect_event('motion_notify_event', self.onmove)
        self.connect_event('button_press_event', self.press)
        self.connect_event('button_release_event', self.release)
        self.connect_event('key_press_event', self.on_key_press)
        self.connect_event('key_release_event', self.on_key_release)
        self.connect_event('scroll_event', self.on_scroll)

        self.state_modifier_keys = dict(move=' ', clear='escape', square='shift', center='control')
        # self.state_modifier_keys.update(state_modifier_keys or {})

        if isinstance(button, int):
            self.validButtons = [button]
        else:
            self.validButtons = button

        # will save the data (position at mouseclick)
        self.eventpress = None
        # will save the data (pos. at mouserelease)
        self.eventrelease = None
        self._prev_event = None
        self.state = set()

    @staticmethod
    @abstractmethod
    def getHelpText():
        return "This Selector has no help text."

    @abstractmethod
    def reset(self):
        pass

    def set_active(self, active):
        AxesWidget.set_active(self, active)
        if active:
            self.axMan._update_background(None)

    def ignore(self, event):
        """return *True* if *event* should be ignored"""
        if not self.active or not self.axMan.ax.get_visible():
            return True
        if not self.canvas.widgetlock.available(self): # If canvas was locked
            return True
        if not hasattr(event, 'button'):
            event.button = None
        if self.validButtons is not None:  # Only do rectangle selection if event was triggered with a desired button
            if event.button not in self.validButtons:
                return True
        if self.eventpress is None:  # If no button was pressed yet ignore the event if it was out of the axes
            return event.inaxes != self.ax
        if event.button == self.eventpress.button:  # If a button was pressed, check if the release-button is the same.
            return False
        # If a button was pressed, check if the release-button is the same.
        return event.inaxes != self.ax or event.button != self.eventpress.button

    def __get_data(self, event):
        """Get the xdata and ydata for event, with limits"""
        if event.xdata is None:
            return None, None
        x0, x1 = self.axMan.ax.get_xbound()
        y0, y1 = self.axMan.ax.get_ybound()
        xdata = max(x0, event.xdata)
        xdata = min(x1, xdata)
        ydata = max(y0, event.ydata)
        ydata = min(y1, ydata)
        return xdata, ydata

    def __clean_event(self, event):
        """Clean up an event
        Use prev event if there is no xdata
        Limit the xdata and ydata to the axes limits
        Set the prev event
        """
        if event.xdata is None:
            event = self._prev_event
        else:
            event = copy.copy(event)
        event.xdata, event.ydata = self.__get_data(event)
        self._prev_event = event
        return event

    def press(self, event):
        """Button press handler and validator"""
        if not self.ignore(event):
            event = self.__clean_event(event)
            self.eventpress = event
            key = event.key or ''
            key = key.replace('ctrl', 'control')
            # move state is locked in on a button press
            if key == self.state_modifier_keys['move']:
                self.state.add('move')
            self._press(event)
            return True
        return False

    def release(self, event):
        """Button release event handler and validator"""
        if not self.ignore(event) and self.eventpress:
            event = self.__clean_event(event)
            self.eventrelease = event
            self._release(event)
            self.eventpress = None
            self.eventrelease = None
            self.state.discard('move')
            return True
        return False

    def onmove(self, event):
        """Cursor move event handler and validator"""
        if not self.ignore(event):
            event = self.__clean_event(event)
            if self.eventpress:
                self._ondrag(event)
            else:
                self._onhover(event)
            return True
        return False

    def on_scroll(self, event):
        """Mouse scroll event handler and validator"""
        if not self.ignore(event):
            self._on_scroll(event)

    def on_key_press(self, event):
        """Key press event handler and validator for all selection widgets"""
        if self.active:
            key = event.key or ''
            key = key.replace('ctrl', 'control')
            if key == self.state_modifier_keys['clear']:
                self.set_visible(False)
                return
            for (state, modifier) in self.state_modifier_keys.items():
                if modifier in key:
                    self.state.add(state)
            self._on_key_press(event)

    def on_key_release(self, event):
        """Key release event handler and validator"""
        if self.active:
            key = event.key or ''
            for (state, modifier) in self.state_modifier_keys.items():
                if modifier in key:
                    self.state.discard(state)
            self._on_key_release(event)

    def set_visible(self, visible):
        """ Set the visibility of our artists """
        self.visible = visible
        for artist in self.artists:
            artist.set_visible(visible)
        self.axMan.draw()

    def addArtist(self, artist):
        """Add a matplotlib artist to be managed."""
        self.axMan.artists.append(artist)
        self.artists.append(artist)
        if isinstance(artist, Patch):
            self.axMan.ax.add_patch(artist)
        elif isinstance(artist, Line2D):
            self.axMan.ax.add_line(artist)
        else:
            self.axMan.ax.add_artist(artist)

    def removeArtists(self):
        for artist in self.artists:
            self.axMan.artists.remove(artist)
            artist.remove()
        self.artists = []
        self.axMan.draw()

    def removeArtist(self, artist):
        self.artists.remove(artist)
        self.axMan.artists.remove(artist)
        artist.remove()
        self.axMan.draw()

    # Overridable events
    def _on_key_release(self, event):
        """Key release event handler"""
        pass
    def _on_key_press(self, event):
        """Key press event handler - use for widget-specific key press actions."""
        pass
    def _on_scroll(self, event):
        """Mouse scroll event handler"""
        pass
    def _ondrag(self, event):
        """Cursor move event handler"""
        pass
    def _onhover(self, event):
        pass
    def _release(self, event):
        """Button release event handler"""
        pass
    def _press(self, event):
        """Button press handler"""
        pass