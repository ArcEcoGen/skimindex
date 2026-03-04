CC = gcc
CFLAGS = -O2 -Wall
TARGET = kmerasm
SRC = kmerasm.c
PREFIX = /bettik/LECA/home/pan/G15X

.PHONY: all install clean

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC)

install: $(TARGET)
	install -m 755 $(TARGET) $(PREFIX)/bin

clean:
	rm -f $(TARGET)
