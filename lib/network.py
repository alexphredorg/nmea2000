#!/usr/bin/python

import threading
import socket
#import Queue
import time
from pprint import pprint
from select import select

#
# This is the network base for a server that broadcasts the same data to
# all clients and doesn't accept input from the clients.
#
class BroadcastServer(object):
    # worker thread
    __thread = None

    # the list of open client sockets
    __sockets = []

    # the socket that we listen for new connections on
    __listen = None

    # output queues for each socket.  The queue is deleted when the 
    # last send has completed.  If the queue doesn't exist for a socket
    # then the send can take place immediately.
    # socket: [ data ]
    __writeQueue = {}

    #
    # Initialize a new server, listening to all bound IP addresses on the
    # assigned port
    #
    # port -- the TCP/IP port to bind to
    # interval -- How often we should run the function that gathers data
    # fn -- The data function to run.  The return value is a string to 
    #   send to all clients.
    # fnConnect -- Called whenever a client connects or disconnects
    #
    def __init__(self, port, interval, fn, fnConnect):
        self.__fn = fn;
        self.__fnConnect = fnConnect;
        self.__interval = interval;

        # create and bind the socket that we use to accept new incoming
        # connections
        self.__listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__listen.bind(('', port))
        self.__listen.listen(5)
        self.__sockets.append(self.__listen)

        # create the thread that handles all IO
        self.__thread = threading.Thread(target=self.__thread_loop)
        self.__thread.daemon = True
        self.__thread.start()

    #
    # This is the core worker thread for the server.  It listens for 
    # incoming data on __consumeRd and sends that data to all attached
    # clients.  It also accepts new clients.
    #
    def __thread_loop(self):
        lastsend = time.process_time()
        while (True):
            timeout = max(self.__interval - (time.process_time() - lastsend), 0)
            readable, writable, exceptional = select(
                self.__sockets, 
                self.__writeQueue.keys(), 
                self.__sockets, 
                timeout)

            # if we haven't send output since the last interval then send it
            # now.  
            if time.process_time() > lastsend + self.__interval:
                lastsend = time.process_time()
                # don't send output if no one is connected
                if len(self.__sockets) > 1:
                    output = self.__fn()
                    for outputSocket in self.__sockets:
                        if outputSocket != self.__listen:
                            self.__send_internal(outputSocket, output)

            # there is incoming data on the socket, a new incoming connection,
            # or a dropped connection
            for s in readable:
                if s is self.__listen:
                    connection, client_address = self.__listen.accept()
                    connection.setblocking(0)
                    self.__sockets.append(connection)
                    if self.__fnConnect != None:
                        self.__fnConnect(len(self.__sockets) - 1)

                else:
                    try:
                        # listen and throw out data, we only publish
                        data = s.recv(1024)
                    except:
                        # on Windows we get an exception on connection 
                        # drop
                        data = 0

                    if data == 0:
                        # connection dropped
                        self.__cleanup_socket(s)

                    # we throw out all other input


            # a write has completed
            for s in writable:
                if self.__writeQueue[s].empty():
                    # we sent out the last item in the queue, delete it
                    del self.__writeQueue[s]
                else:
                    # get the next item to send
                    data = self.__writeQueue[s].get_nowait()
                    try:
                        s.send(data)
                    except:
                        self.__cleanup_socket(s)

            # socket closed
            for s in exceptional:
                self.__cleanup_socket(s)

    #
    # internal function that cleans up all outstanding state for a socket
    #
    def __cleanup_socket(self, s):
        s.close()
        self.__sockets.remove(s)
        if self.__fnConnect != None:
            self.__fnConnect(len(self.__sockets) - 1)
        if s in self.__writeQueue:
            del self.__writeQueue[s]

    #
    # Send data to one of the associated sockets.  This also maintains
    # the write queue.
    #
    def __send_internal(self, outputSocket, data):
        if outputSocket not in self.__writeQueue:
            # no output queue, create one and send data
            try:
                outputSocket.send(data)
                self.__writeQueue[outputSocket] = Queue.Queue()
            except:
                outputSocket.close()
        else:
            self.__writeQueue[outputSocket].put_nowait(data)
        
