import threading
import time

# 
# A wrapper class to run a function on a periodic basis on it's own thread
#
class RepeatTimer(object):
    # 
    # interval -- period (measured in seconds) between runs of the function
    # fn -- the function to run
    #
    def __init__(self, interval, fn):
        self.__interval = interval
        self.__fn = fn
        self.__thread = threading.Thread(target=self.handle_function)
        self.__thread.daemon = True
        self.__thread.start()


    # 
    # This is the main body of the thread
    #
    def handle_function(self):
        while (1):
            time.sleep(self.__interval)
            self.__fn()

