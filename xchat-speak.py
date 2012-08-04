__module_name__ = "xchat-speak"
__module_version__ = "1.0"
__module_description__ = "speak using festival"

import socket
import os
import time
import atexit
import signal
import xchat
import string
import re
import pickle

class festival:
    "Festival object"

    def __init__(self):
        self.festival_pid = 0
        self.sock = self.open()
        self.block(False)

    def _checkresp(self):
        if self.sock.recv(256)=='ER\n':
            raise Exception

    def set_param(self,param,value):
        "Set parameter to a number or a symbol."

        if type(value) is str:
            self.sock.send("(Parameter.set '%s '%s)"%(param,value))
        else:
            self.sock.send("(Parameter.set '%s %r)"%(param,value))
        self._checkresp()

    def set_param_str(self,param,value):
        "Set parameter to a string."

        self.sock.send("(Parameter.set '%s \"%s\")"%(param,value))
        self._checkresp()

    def block(self,flag=True):
        "Sets blocking/nonblocking mode."

        if flag:
            self.sock.send("(audio_mode 'sync)")
        else:
            self.sock.send("(audio_mode 'async)")
        self._checkresp()

    def set_audio_method(self,method=None,device=None):
        "Set audio method and/or device."

        if method is not None:
            self.set_param('Audio_Method',method)
        if device is not None:
            self.set_param_str('Audio_Device',device)

    def set_audio_command(self,command,rate=None,format=None):
        """Set audio command, and optionally rate and format.

        Sets audio method to "Audio_Command"."""

        self.set_audio_method("Audio_Command")
        if rate is not None:
            self.set_param('Audio_Required_Rate',rate)
        if format is not None:
            self.set_param('Audio_Required_Format',format)
        self.set_param_str('Audio_Command',command)

    def say(self,text,actor=None):
        "Speak string 'text'."
        if actor: self.sock.send(actor)
        self.sock.send('(SayText "%s")' % re.sub(r'"',r'\"',text))
        # this makes xchat block while speaking. bad.
        #self._checkresp()

    def sayfile(self,filename):
        """Speak contents of file 'filename'.

        Note that this is done on the server end, not the client
        end, so you best pass it absolute filenames."""

        self.sock.send('(tts "%s" nil)'%filename)
        self._checkresp()

    def close(self):
        "Terminate the Festival connection."
        self.sock.send('(quit)')

    def open(self,host='',port=1314,nostart=False):
        """Opens a new connection to a Festival server.

        Attempts to connect to a Festival server (most likely started with
        'festival --server'). Will attempt to start a local server on port
        1314 if one is not running and the 'nostart' flag is not set to
        True. Returns a festival.festival object."""

        from subprocess import STDOUT, Popen

        sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            sock.connect((host,port))
        except socket.error:
            if nostart:
                raise socket.error
            else:
                self.festival_pid = Popen(["festival", "--server"]).pid
                atexit.register(self._kill_server)
                for t in xrange(20):
                    try:
                        time.sleep(.25)
                        sock.connect((host,port))
                    except socket.error:
                        pass
                    else:
                        break
                else:
                    raise socket.error

        self.sock = sock
        return sock

    def _kill_server(self):
        if (self.festival_pid):
            os.kill(self.festival_pid,signal.SIGTERM)
            self.festival_pid = 0


def unscramble_nick(speaker):
    speakable_speaker = re.sub(r'^:(.*?)!.*', r'\1',speaker)
    return speakable_speaker

class xchat_speak:
    def __del__(self):
        self.pack()

    def __init__(self):
        # fix find a way to remove use of globals
        self.festival=festival()
        self.vocalized_channels = set()
        self.vocalized_nicks = set()
        self.muted_nicks_in_channels = set()

        self.actors = {
            "caleb" : "(voice_kal_diphone)",
            "ken" : "(voice_ked_diphone)",
            "randal" : "(voice_rab_diphone)",
            "alan" : "(voice_cmu_us_awb_arctic_clunits)",
            "brett" : "(voice_cmu_us_bdl_arctic_clunits)",
            "carmen" : "(voice_cmu_us_clb_arctic_clunits)",
            "jerry" : "(voice_cmu_us_jmk_arctic_clunits)",
            "roger" : "(voice_cmu_us_rms_arctic_clunits)",
            "sarah" : "(voice_cmu_us_slt_arctic_clunits)",
            }

        self.unpack()
        self.substitutions={
            }

        xchat.hook_command("unmute", self.unmute, help="/unmute [speaker] Turn on speech for this window or a specific speaker in this channel")
        xchat.hook_command("mute", self.mute, help="/mute [speaker] Turn off speech for this window, or mute a specific speaker in this channel")
        xchat.hook_command("pronounce", self.pronounce, help="'/pronounce word [pronounciation]' - Fix pronounciation for a word, or delete the pronounciation if it exists.")
        xchat.hook_command("cast", self.cast, help="'/cast nick [actor]' cast an actor as a particular nick, or clear that casting.")
        xchat.hook_server("PRIVMSG", self.chat_hook)

    def pickle_database(self):
        return os.path.join(xchat.get_info("xchatdir"),"pronounciation_database.pickle")

    def clean(self,message):
        words = message.split()
        cleaned = []
        for word in words:
            lower_word = word.lower()
            if lower_word in self.spell:
                word = self.spell[lower_word]
            cleaned.append(word)
        message = " ".join(cleaned)

        for (regex, result) in self.substitutions.items():
            message = re.sub(regex, result, message)

        return message

    def pack(self):
        p = pickle.Pickler(open(self.pickle_database(),"w"))
        p.dump(self.spell)
        p.dump(self.roles)

    def unpack(self):
        p = pickle.Unpickler(open(self.pickle_database(),"r"))
        self.spell = p.load()
        self.roles = p.load()

    def pronounce(self, word, word_eol, userdata):
        "'/pronounce word [pronounciation]' - Fix pronounciation for a word, or delete the pronounciation if it exists."
        if (len(word) <= 1):
            return xchat.EAT_ALL
        mispronounced_word = word[1]
        new_pronounciation = " ".join(word[2:])
        if not new_pronounciation:
            if self.spell.has_key(mispronounced_word):
                del self.spell[mispronounced_word]
            print mispronounced_word+" pronounciation cleared."
        else:
            self.spell[mispronounced_word] = new_pronounciation
            print "pronounciation stored: "+mispronounced_word+" ==> "+new_pronounciation
        return xchat.EAT_ALL

    def unmute(self, word, word_eol, userdata):
        "/unmute [speaker] Turn on speech for this window or a specific speaker in this channel"
        target = xchat.get_info('channel')
        if (len(word) == 1):
            if re.match('#',target):
                self.vocalized_channels.add(target)
                xchat.prnt('Speaking for channel '+target)
            else:
                self.vocalized_nicks.add(target)
                xchat.prnt('Speaking user '+target)
        else:
            for speaker in word[1:]:
                self.muted_nicks_in_channels.discard(speaker)
                xchat.prnt('Unsilencing user '+speaker+' in all channels')
        return xchat.EAT_ALL

    def mute(self, word, word_eol, userdata):
        "/mute [speaker] Turn off speech for this window, or mute a specific speaker in this channel"
        target = xchat.get_info('channel')
        if (len(word) == 1):
            if re.match('#',target):
                self.vocalized_channels.discard(target)
                xchat.prnt('Muting channel '+target)
            else:
                self.vocalized_nicks.discard(target)
                xchat.prnt('Muting user '+target)
        else:
            for speaker in word[1:]:
                self.muted_nicks_in_channels.add(speaker)
                xchat.prnt('Silencing user '+speaker+' in all channels')
        return xchat.EAT_ALL

    def cast(self, word, word_eol, userdata):
        "'/cast nick [actor]' cast an actor as a particular nick, or clear that casting."
        if len(word) >= 2:
            nick = word[1]
            if len(word) == 2:
                if self.roles.has_key(nick):
                    del self.roles[nick]
                print "Clearing casting of "+nick
            else:
                actor = word[2]
                if self.actors.has_key(actor):
                    self.roles[nick] = self.actors[actor]
                    print "Casting "+nick+" as "+actor
                else:
                    print "Unrecognized actor: "+actor
        return xchat.EAT_ALL

    def chat_hook(self, word, word_eol, userdata):
        speaker = unscramble_nick(word[0])
        target = word[2]
        is_private_message = target[0] != '#'
        if ((is_private_message and speaker in self.vocalized_nicks)
            or
            (not is_private_message 
             and target in self.vocalized_channels
             and speaker not in self.muted_nicks_in_channels
             )):
            message = word_eol[3]
            message = re.sub(r'^:(.)ACTION',r':\1'+speaker,message)
            message = self.clean(message)
            
            actor = self.actors["caleb"]
            if self.roles.has_key(speaker):
                actor = self.roles[speaker]
            self.festival.say(message,actor)
        return xchat.EAT_NONE


def _unload(*args):
    global x
    del x

x = xchat_speak()
xchat.hook_unload(_unload)

# /load xchat-speak.py
# /unload xchat-speak.py
